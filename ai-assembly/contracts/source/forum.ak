/// Forum Validator - Discussions, comments, and petitions
///
/// EVM equivalent: Forum.sol

use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/interval.{Finite}
use cardano/transaction.{OutputReference, Transaction, InlineDatum}

pub type ForumConfig {
  petition_threshold_bps: Int,
  admin_pkh: VerificationKeyHash,
  thread_count: Int,
  comment_count: Int,
  petition_count: Int,
}

pub type ThreadDatum {
  thread_id: Int,
  author: VerificationKeyHash,
  created_at: Int,
  title: ByteArray,
  body: ByteArray,
}

pub type CommentDatum {
  comment_id: Int,
  thread_id: Int,
  parent_id: Int,
  author: VerificationKeyHash,
  created_at: Int,
  body: ByteArray,
}

pub type PetitionDatum {
  petition_id: Int,
  proposer: VerificationKeyHash,
  created_at: Int,
  title: ByteArray,
  body: ByteArray,
  signature_count: Int,
  promoted: Bool,
  thread_id: Int,
}

pub type PetitionSignatureDatum {
  petition_id: Int,
  signer: VerificationKeyHash,
}

pub type ForumDatum {
  FConfig(ForumConfig)
  FThread(ThreadDatum)
  FComment(CommentDatum)
  FPetition(PetitionDatum)
  FSignature(PetitionSignatureDatum)
}

pub type ForumAction {
  PostThread
  PostComment
  CreatePetition
  SignPetition
  PromotePetition
  UpdateForumConfig
}

validator forum {
  spend(
    datum_opt: Option<ForumDatum>,
    redeemer: ForumAction,
    _own_ref: OutputReference,
    tx: Transaction,
  ) {
    expect Some(datum) = datum_opt
    when redeemer is {
      PostThread -> validate_post_thread(datum, tx)
      PostComment -> validate_post_comment(datum, tx)
      CreatePetition -> validate_create_petition(datum, tx)
      SignPetition -> validate_sign_petition(datum, tx)
      PromotePetition -> validate_promote_petition(datum, tx)
      UpdateForumConfig -> validate_update_forum(datum, tx)
    }
  }

  else(_) {
    fail
  }
}

fn validate_post_thread(datum: ForumDatum, tx: Transaction) -> Bool {
  expect FConfig(config) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type

  let config_updated =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: ForumDatum = d
            when out_datum is {
              FConfig(new_config) ->
                new_config.thread_count == config.thread_count + 1 && new_config.comment_count == config.comment_count && new_config.petition_count == config.petition_count && new_config.admin_pkh == config.admin_pkh
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  let thread_created =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: ForumDatum = d
            when out_datum is {
              FThread(thread) ->
                thread.thread_id == config.thread_count + 1 && thread.created_at == now && list.has(tx.extra_signatories, thread.author)
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  config_updated && thread_created
}

fn validate_post_comment(datum: ForumDatum, tx: Transaction) -> Bool {
  expect FConfig(config) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type

  let config_updated =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: ForumDatum = d
            when out_datum is {
              FConfig(new_config) ->
                new_config.comment_count == config.comment_count + 1 && new_config.thread_count == config.thread_count && new_config.petition_count == config.petition_count
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  let comment_created =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: ForumDatum = d
            when out_datum is {
              FComment(comment) ->
                comment.comment_id == config.comment_count + 1 && comment.created_at == now && list.has(tx.extra_signatories, comment.author)
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  config_updated && comment_created
}

fn validate_create_petition(datum: ForumDatum, tx: Transaction) -> Bool {
  expect FConfig(config) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type

  let config_updated =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: ForumDatum = d
            when out_datum is {
              FConfig(new_config) ->
                new_config.petition_count == config.petition_count + 1 && new_config.thread_count == config.thread_count + 1
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  let petition_created =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: ForumDatum = d
            when out_datum is {
              FPetition(petition) ->
                petition.petition_id == config.petition_count + 1 && petition.signature_count == 1 && !petition.promoted && list.has(tx.extra_signatories, petition.proposer)
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  config_updated && petition_created
}

fn validate_sign_petition(datum: ForumDatum, tx: Transaction) -> Bool {
  expect FPetition(petition) = datum
  let not_promoted = !petition.promoted
  let has_signer = !list.is_empty(tx.extra_signatories)

  let petition_updated =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: ForumDatum = d
            when out_datum is {
              FPetition(new_petition) ->
                new_petition.petition_id == petition.petition_id && new_petition.signature_count == petition.signature_count + 1
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  let signature_created =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: ForumDatum = d
            when out_datum is {
              FSignature(sig) -> sig.petition_id == petition.petition_id
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  not_promoted && has_signer && petition_updated && signature_created
}

fn validate_promote_petition(datum: ForumDatum, _tx: Transaction) -> Bool {
  expect FPetition(petition) = datum
  !petition.promoted
}

fn validate_update_forum(datum: ForumDatum, tx: Transaction) -> Bool {
  expect FConfig(config) = datum
  list.has(tx.extra_signatories, config.admin_pkh)
}
