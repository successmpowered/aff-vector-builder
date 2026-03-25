/// Governance Validator - Proposal lifecycle
///
/// Deliberation -> Voting -> Timelock -> Execution
/// EVM equivalent: Governance.sol

use ai_assembly/types.{
  ProposalKind, ProposalStatus, ProposalOrigin, VoteChoice, RiskTier,
  ConfigUpdate, ConfigChange, Dissolution, IntentBundle,
  Deliberation, Voting, Timelock, Executed, Defeated, Cancelled,
  Against, For, Abstain, Council, Petition,
  Routine, Significant, Major, Constitutional,
}
use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/interval.{Finite}
use cardano/transaction.{OutputReference, Transaction, InlineDatum}

pub type GovernanceConfig {
  quorum_bps: Int,
  significant_pass_bps: Int,
  major_pass_bps: Int,
  constitutional_pass_bps: Int,
  deliberation_period: Int,
  vote_period: Int,
  timelock_period: Int,
  admin_pkh: VerificationKeyHash,
  proposal_count: Int,
}

pub type ProposalDatum {
  proposal_id: Int,
  kind: ProposalKind,
  origin: ProposalOrigin,
  status: ProposalStatus,
  proposer: VerificationKeyHash,
  created_at: Int,
  deliberation_ends_at: Int,
  vote_start_at: Int,
  vote_end_at: Int,
  timelock_ends_at: Int,
  active_seats_snapshot: Int,
  for_votes: Int,
  against_votes: Int,
  abstain_votes: Int,
  risk_tier: RiskTier,
  config_updates: List<ConfigUpdate>,
  description_hash: ByteArray,
}

pub type VoteReceiptDatum {
  proposal_id: Int,
  voter: VerificationKeyHash,
  choice: VoteChoice,
  weight: Int,
}

pub type GovernanceDatum {
  GovConfig(GovernanceConfig)
  GovProposal(ProposalDatum)
  GovVoteReceipt(VoteReceiptDatum)
}

pub type GovernanceAction {
  SubmitProposal
  MoveToVoting
  CastVote { choice: VoteChoice, weight: Int }
  FinalizeVote
  ExecuteProposal
  UpdateGovConfig
}

const bps_denominator: Int = 10_000

validator governance {
  spend(
    datum_opt: Option<GovernanceDatum>,
    redeemer: GovernanceAction,
    _own_ref: OutputReference,
    tx: Transaction,
  ) {
    expect Some(datum) = datum_opt
    when redeemer is {
      SubmitProposal -> validate_submit(datum, tx)
      MoveToVoting -> validate_move_to_voting(datum, tx)
      CastVote { choice, weight } -> validate_cast_vote(datum, tx, choice, weight)
      FinalizeVote -> validate_finalize_vote(datum, tx)
      ExecuteProposal -> validate_execute(datum, tx)
      UpdateGovConfig -> validate_update_gov(datum, tx)
    }
  }

  else(_) {
    fail
  }
}

fn validate_submit(datum: GovernanceDatum, tx: Transaction) -> Bool {
  expect GovConfig(config) = datum

  // Config reproduced with incremented count
  let config_updated =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: GovernanceDatum = d
            when out_datum is {
              GovConfig(new_config) ->
                new_config.proposal_count == config.proposal_count + 1 && new_config.admin_pkh == config.admin_pkh
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  // New proposal created in Deliberation
  let proposal_created =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: GovernanceDatum = d
            when out_datum is {
              GovProposal(p) ->
                p.status == Deliberation && p.proposal_id == config.proposal_count + 1 && p.for_votes == 0 && p.against_votes == 0 && p.abstain_votes == 0
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  config_updated && proposal_created
}

fn validate_move_to_voting(datum: GovernanceDatum, tx: Transaction) -> Bool {
  expect GovProposal(proposal) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type

  let in_deliberation = proposal.status == Deliberation
  let deliberation_over = now >= proposal.deliberation_ends_at

  let moved =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: GovernanceDatum = d
            when out_datum is {
              GovProposal(new_p) ->
                new_p.proposal_id == proposal.proposal_id && new_p.status == Voting && new_p.vote_start_at == now && new_p.active_seats_snapshot > 0
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  in_deliberation && deliberation_over && moved
}

fn validate_cast_vote(
  datum: GovernanceDatum,
  tx: Transaction,
  choice: VoteChoice,
  weight: Int,
) -> Bool {
  expect GovProposal(proposal) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type

  let in_voting = proposal.status == Voting
  let within_window = now < proposal.vote_end_at
  let has_signer = !list.is_empty(tx.extra_signatories)

  // Updated vote tallies
  let votes_updated =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: GovernanceDatum = d
            when out_datum is {
              GovProposal(new_p) -> {
                let correct_tally =
                  when choice is {
                    For ->
                      new_p.for_votes == proposal.for_votes + weight && new_p.against_votes == proposal.against_votes && new_p.abstain_votes == proposal.abstain_votes
                    Against ->
                      new_p.for_votes == proposal.for_votes && new_p.against_votes == proposal.against_votes + weight && new_p.abstain_votes == proposal.abstain_votes
                    Abstain ->
                      new_p.for_votes == proposal.for_votes && new_p.against_votes == proposal.against_votes && new_p.abstain_votes == proposal.abstain_votes + weight
                  }
                new_p.proposal_id == proposal.proposal_id && new_p.status == Voting && correct_tally
              }
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  // Vote receipt created
  let receipt_created =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: GovernanceDatum = d
            when out_datum is {
              GovVoteReceipt(receipt) ->
                receipt.proposal_id == proposal.proposal_id && receipt.choice == choice && receipt.weight == weight
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  in_voting && within_window && has_signer && votes_updated && receipt_created
}

fn validate_finalize_vote(datum: GovernanceDatum, tx: Transaction) -> Bool {
  expect GovProposal(proposal) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type

  let in_voting = proposal.status == Voting
  let vote_over = now >= proposal.vote_end_at

  let total_votes =
    proposal.for_votes + proposal.against_votes + proposal.abstain_votes
  let quorum_met =
    total_votes * bps_denominator >= proposal.active_seats_snapshot * 2500

  let pass_threshold =
    when proposal.risk_tier is {
      Routine -> 5001
      Significant -> 6000
      Major -> 7500
      Constitutional -> 8000
    }

  let total_decided = proposal.for_votes + proposal.against_votes
  let passed =
    if total_decided == 0 {
      False
    } else {
      quorum_met && proposal.for_votes * bps_denominator >= total_decided * pass_threshold
    }

  let expected_status =
    if passed {
      Timelock
    } else {
      Defeated
    }

  let status_updated =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: GovernanceDatum = d
            when out_datum is {
              GovProposal(new_p) ->
                new_p.proposal_id == proposal.proposal_id && new_p.status == expected_status
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  in_voting && vote_over && status_updated
}

fn validate_execute(datum: GovernanceDatum, tx: Transaction) -> Bool {
  expect GovProposal(proposal) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type

  let in_timelock = proposal.status == Timelock
  let timelock_over = now >= proposal.timelock_ends_at

  let marked_executed =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: GovernanceDatum = d
            when out_datum is {
              GovProposal(new_p) ->
                new_p.proposal_id == proposal.proposal_id && new_p.status == Executed
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  in_timelock && timelock_over && marked_executed
}

fn validate_update_gov(datum: GovernanceDatum, tx: Transaction) -> Bool {
  expect GovConfig(config) = datum
  list.has(tx.extra_signatories, config.admin_pkh)
}
