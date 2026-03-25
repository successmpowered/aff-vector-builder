/// Council Validator - Seat auctions and voting power
///
/// 4 seats auctioned per day in 6-hour slots. Winners get 45-day terms.
/// EVM equivalent: CouncilSeats.sol

use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/interval.{Finite}
use cardano/transaction.{OutputReference, Transaction, InlineDatum}

pub type CouncilConfig {
  epoch_start: Int,
  slot_duration: Int,
  slots_per_day: Int,
  seat_term: Int,
  treasury_pkh: VerificationKeyHash,
  admin_pkh: VerificationKeyHash,
  seat_count: Int,
}

pub type AuctionDatum {
  day: Int,
  slot: Int,
  highest_bidder: Option<VerificationKeyHash>,
  highest_bid: Int,
  settled: Bool,
}

pub type SeatDatum {
  seat_id: Int,
  owner: VerificationKeyHash,
  start_at: Int,
  end_at: Int,
  forfeited: Bool,
}

pub type RefundDatum {
  recipient: VerificationKeyHash,
  amount: Int,
}

pub type CouncilDatum {
  CConfig(CouncilConfig)
  CAuction(AuctionDatum)
  CSeat(SeatDatum)
  CRefund(RefundDatum)
}

pub type CouncilAction {
  Bid
  Settle
  Forfeit
  WithdrawRefund
  UpdateCouncilConfig
}

validator council {
  spend(
    datum_opt: Option<CouncilDatum>,
    redeemer: CouncilAction,
    _own_ref: OutputReference,
    tx: Transaction,
  ) {
    expect Some(datum) = datum_opt
    when redeemer is {
      Bid -> validate_bid(datum, tx)
      Settle -> validate_settle(datum, tx)
      Forfeit -> validate_forfeit(datum, tx)
      WithdrawRefund -> validate_withdraw_refund(datum, tx)
      UpdateCouncilConfig -> validate_update_council_config(datum, tx)
    }
  }

  else(_) {
    fail
  }
}

fn validate_bid(datum: CouncilDatum, tx: Transaction) -> Bool {
  expect CAuction(auction) = datum
  let not_settled = !auction.settled
  let has_signer = !list.is_empty(tx.extra_signatories)

  // Must produce updated auction with higher bid
  let bid_updated =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: CouncilDatum = d
            when out_datum is {
              CAuction(new_auction) ->
                new_auction.day == auction.day && new_auction.slot == auction.slot && !new_auction.settled && new_auction.highest_bid > auction.highest_bid
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  // If previous bidder exists, must create refund
  let refund_handled =
    when auction.highest_bidder is {
      None -> True
      Some(prev_bidder) ->
        list.any(
          tx.outputs,
          fn(output) {
            when output.datum is {
              InlineDatum(d) -> {
                expect out_datum: CouncilDatum = d
                when out_datum is {
                  CRefund(refund) ->
                    refund.recipient == prev_bidder && refund.amount == auction.highest_bid
                  _ -> False
                }
              }
              _ -> False
            }
          },
        )
    }

  not_settled && has_signer && bid_updated && refund_handled
}

fn validate_settle(datum: CouncilDatum, tx: Transaction) -> Bool {
  expect CAuction(auction) = datum
  let not_settled = !auction.settled

  let auction_marked_settled =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: CouncilDatum = d
            when out_datum is {
              CAuction(new_auction) ->
                new_auction.day == auction.day && new_auction.slot == auction.slot && new_auction.settled
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  // If winner exists, must create seat
  let winner_handled =
    when auction.highest_bidder is {
      None -> True
      Some(winner) ->
        list.any(
          tx.outputs,
          fn(output) {
            when output.datum is {
              InlineDatum(d) -> {
                expect out_datum: CouncilDatum = d
                when out_datum is {
                  CSeat(seat) -> seat.owner == winner && !seat.forfeited
                  _ -> False
                }
              }
              _ -> False
            }
          },
        )
    }

  not_settled && auction_marked_settled && winner_handled
}

fn validate_forfeit(datum: CouncilDatum, tx: Transaction) -> Bool {
  expect CSeat(seat) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type
  let not_forfeited = !seat.forfeited
  let expired = seat.end_at < now

  let seat_marked_forfeited =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: CouncilDatum = d
            when out_datum is {
              CSeat(new_seat) ->
                new_seat.seat_id == seat.seat_id && new_seat.forfeited
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  not_forfeited && expired && seat_marked_forfeited
}

fn validate_withdraw_refund(datum: CouncilDatum, tx: Transaction) -> Bool {
  expect CRefund(refund) = datum
  list.has(tx.extra_signatories, refund.recipient)
}

fn validate_update_council_config(datum: CouncilDatum, tx: Transaction) -> Bool {
  expect CConfig(config) = datum
  list.has(tx.extra_signatories, config.admin_pkh)
}
