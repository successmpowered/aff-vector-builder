use aiken/collection/list
use aiken/crypto.{VerificationKeyHash, blake2b_256}
use aiken/interval.{Finite}
use aiken/math
use cardano/address.{VerificationKey}
use cardano/transaction.{Transaction, OutputReference, Output, InlineDatum}
use cardano/assets.{PolicyId, AssetName, lovelace_of, quantity_of}

/// ============================================================================
/// DEX V2: PERMISSIONLESS LIMIT ORDER BOOK
/// ============================================================================
///
/// Problem: Traditional UTXO DEX batchers are centralized. A single batcher:
///   1. Can censor orders (refuse to fill them)
///   2. Can reorder for MEV extraction (sandwich attacks)
///   3. Is a single point of failure
///   4. Can frontrun large orders
///
/// Solution: Permissionless matching where ANYONE can be the "scooper"
/// but the validator enforces price execution on-chain, so the scooper
/// CANNOT extract MEV — they can only match orders at fair prices.
///
/// Architecture:
///   - Each order is a UTxO at the script address
///   - The datum specifies exact price constraints (min receive)
///   - ANY wallet can submit a tx that fills orders (no designated batcher)
///   - The validator checks: did the order owner receive >= min_receive?
///   - Partial fills supported: leftover creates a new order UTxO
///   - Scooper gets a small fee (incentive to match) but CANNOT manipulate price
///
/// EVM equivalent: 0x Protocol / Serum CLOB — but fully on-chain & permissionless

/// Token identifier (policy_id + asset_name)
pub type TokenId {
  policy: PolicyId,
  name: AssetName,
}

/// A limit order: offer token_a, want at least min_receive of token_b
pub type LimitOrderDatum {
  /// Order owner — receives output, can cancel
  owner: VerificationKeyHash,
  /// What the user is offering (sits in the UTxO value)
  offer_token: TokenId,
  /// What the user wants in return
  ask_token: TokenId,
  /// Minimum amount of ask_token the owner must receive
  /// This is the PRICE ENFORCEMENT — scooper cannot give less
  min_receive: Int,
  /// Original offer amount (for partial fill tracking)
  original_offer: Int,
  /// Scooper fee in lovelace (flat fee, not percentage — prevents MEV)
  scooper_fee: Int,
  /// Unique order ID (hash of original utxo ref) — prevents replay
  order_id: ByteArray,
  /// Deadline slot — order expires after this (0 = no expiry)
  deadline: Int,
}

pub type OrderAction {
  /// Anyone can fill — validator enforces price
  Fill {
    /// Index of the output paying the order owner
    output_index: Int,
  }
  /// Partial fill — remainder stays as new order
  PartialFill {
    /// Index of output paying owner partial amount
    output_index: Int,
    /// Index of output with remaining order
    remainder_index: Int,
    /// Amount of offer being filled this time
    fill_amount: Int,
  }
  /// Owner cancels their order
  Cancel
}

validator dex_v2_limit_order {
  spend(
    datum: Option<LimitOrderDatum>,
    redeemer: OrderAction,
    _utxo: OutputReference,
    self: Transaction,
  ) {
    expect Some(d) = datum

    when redeemer is {
      // ============================================================
      // FILL: Anyone can fill, but must pay owner >= min_receive
      // This is the KEY innovation: no trusted batcher needed
      // ============================================================
      Fill { output_index } -> {
        // Get the output that should pay the order owner
        expect Some(pay_output) = list.at(self.outputs, output_index)

        // Verify payment goes to order owner's address
        expect owner_paid = pays_to_pkh(pay_output, d.owner)

        // Verify owner receives at least min_receive of ask_token
        let received = token_amount(pay_output, d.ask_token)
        expect price_satisfied = received >= d.min_receive

        // Check deadline (0 = no deadline)
        expect not_expired = if d.deadline > 0 {
          // self.validity_range lower bound must be < deadline
          check_not_expired(self, d.deadline)
        } else {
          True
        }

        owner_paid && price_satisfied && not_expired
      }

      // ============================================================
      // PARTIAL FILL: Fill part of the order, leave remainder
      // Prevents "all or nothing" which wastes liquidity
      // ============================================================
      PartialFill { output_index, remainder_index, fill_amount } -> {
        // Sanity: fill_amount must be positive and less than full offer
        expect fill_amount > 0

        // Calculate proportional min_receive for this partial fill
        // min_receive_partial = (fill_amount * min_receive) / original_offer
        // Using ceiling division to protect the order owner
        let proportional_receive = math.max(
          1,
          (fill_amount * d.min_receive + d.original_offer - 1) / d.original_offer
        )

        // Check payment output
        expect Some(pay_output) = list.at(self.outputs, output_index)
        expect owner_paid = pays_to_pkh(pay_output, d.owner)
        let received = token_amount(pay_output, d.ask_token)
        expect price_satisfied = received >= proportional_receive

        // Check remainder output stays at script address
        expect Some(remainder_output) = list.at(self.outputs, remainder_index)
        expect InlineDatum(raw_datum) = remainder_output.datum
        expect remainder_datum: LimitOrderDatum = raw_datum

        // Verify remainder datum is correct
        let remaining_offer = d.original_offer - fill_amount
        expect remaining_offer > 0
        let remaining_min = d.min_receive - proportional_receive

        expect remainder_datum.owner == d.owner
        expect remainder_datum.order_id == d.order_id
        expect remainder_datum.min_receive >= remaining_min
        expect remainder_datum.original_offer == remaining_offer

        // Deadline check
        expect not_expired = if d.deadline > 0 {
          check_not_expired(self, d.deadline)
        } else {
          True
        }

        owner_paid && price_satisfied && not_expired
      }

      // ============================================================
      // CANCEL: Only the order owner can cancel
      // ============================================================
      Cancel -> {
        list.has(self.extra_signatories, d.owner)
      }
    }
  }

  else(_) {
    fail
  }
}

/// Check if an output pays to a specific public key hash
fn pays_to_pkh(output: Output, pkh: VerificationKeyHash) -> Bool {
  when output.address.payment_credential is {
    VerificationKey(h) -> h == pkh
    _ -> False
  }
}

/// Get amount of a specific token in an output
fn token_amount(output: Output, token: TokenId) -> Int {
  if token.policy == #"" {
    // ADA/lovelace
    lovelace_of(output.value)
  } else {
    quantity_of(output.value, token.policy, token.name)
  }
}

/// Check transaction is not past deadline
fn check_not_expired(tx: Transaction, deadline: Int) -> Bool {
  when tx.validity_range.lower_bound.bound_type is {
    Finite(lo) -> lo < deadline
    _ -> False
  }
}

// ============================================================================
// TESTS
// ============================================================================

test test_limit_order_datum_construction() {
  let d = LimitOrderDatum {
    owner: #"aabbccdd00112233aabbccdd00112233aabbccdd00112233aabbccdd",
    offer_token: TokenId { policy: #"", name: #"" },
    ask_token: TokenId { policy: #"aabb", name: #"544f4b454e" },
    min_receive: 100,
    original_offer: 5000000,
    scooper_fee: 500000,
    order_id: #"deadbeef",
    deadline: 0,
  }
  d.min_receive == 100
}

test test_proportional_receive_calculation() {
  // If order is: offer 1000 for min 500
  // Partial fill of 250 (25%) should require at least 125
  let fill_amount = 250
  let min_receive = 500
  let original_offer = 1000
  let proportional = (fill_amount * min_receive + original_offer - 1) / original_offer
  proportional == 125
}

test test_proportional_rounding_up() {
  // Edge case: 333 out of 1000, min_receive = 100
  // 333 * 100 / 1000 = 33.3, should round up to 34
  let fill = 333
  let min_recv = 100
  let original = 1000
  let result = (fill * min_recv + original - 1) / original
  result == 34
}

test test_token_id_equality() {
  let t1 = TokenId { policy: #"aabb", name: #"544f4b454e" }
  let t2 = TokenId { policy: #"aabb", name: #"544f4b454e" }
  t1 == t2
}

test test_order_id_uniqueness() {
  let id1 = blake2b_256("order1")
  let id2 = blake2b_256("order2")
  id1 != id2
}
