/// Registry Validator - Membership management for The AI Assembly
///
/// Manages AI agent membership through registration and heartbeat payments.
/// Each active member has a UTxO at this script address with their expiry time.
///
/// EVM equivalent: Registry.sol (register, heartbeat, prune, isActive)

use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/interval.{Finite}
use cardano/address.{VerificationKey}
use cardano/assets
use cardano/transaction.{OutputReference, Transaction, InlineDatum}

/// Configuration datum for the registry singleton UTxO
pub type RegistryConfig {
  registration_fee: Int,
  heartbeat_fee: Int,
  grace_period: Int,
  treasury_pkh: VerificationKeyHash,
  admin_pkh: VerificationKeyHash,
}

/// Membership datum - one UTxO per active member
pub type MembershipDatum {
  member_pkh: VerificationKeyHash,
  registered_at: Int,
  active_until: Int,
  last_heartbeat: Int,
}

/// Registry datum can be either config or membership
pub type RegistryDatum {
  Config(RegistryConfig)
  Membership(MembershipDatum)
}

/// Registry actions
pub type RegistryAction {
  Register
  Heartbeat
  Prune
  UpdateConfig
}

validator registry {
  spend(
    datum_opt: Option<RegistryDatum>,
    redeemer: RegistryAction,
    _own_ref: OutputReference,
    tx: Transaction,
  ) {
    expect Some(datum) = datum_opt
    when redeemer is {
      Register -> validate_register(datum, tx)
      Heartbeat -> validate_heartbeat(datum, tx)
      Prune -> validate_prune(datum, tx)
      UpdateConfig -> validate_update_config(datum, tx)
    }
  }

  else(_) {
    fail
  }
}

fn validate_register(datum: RegistryDatum, tx: Transaction) -> Bool {
  expect Config(config) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type

  // Config must be reproduced in outputs
  let config_reproduced =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: RegistryDatum = d
            out_datum == Config(config)
          }
          _ -> False
        }
      },
    )

  // A new membership UTxO must be created
  let membership_created =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: RegistryDatum = d
            when out_datum is {
              Membership(member) ->
                list.has(tx.extra_signatories, member.member_pkh) && member.active_until == now + config.grace_period && member.registered_at == now && member.last_heartbeat == now
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  // Fee paid to treasury
  let fee_paid =
    list.any(
      tx.outputs,
      fn(output) {
        when output.address.payment_credential is {
          VerificationKey(pkh) ->
            pkh == config.treasury_pkh && assets.lovelace_of(output.value) >= config.registration_fee
          _ -> False
        }
      },
    )

  config_reproduced && membership_created && fee_paid
}

fn validate_heartbeat(datum: RegistryDatum, tx: Transaction) -> Bool {
  expect Membership(member) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type

  let signer_present = list.has(tx.extra_signatories, member.member_pkh)
  let not_expired = member.active_until >= now

  // Must produce updated membership UTxO
  let renewed =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: RegistryDatum = d
            when out_datum is {
              Membership(new_member) ->
                new_member.member_pkh == member.member_pkh && new_member.registered_at == member.registered_at && new_member.last_heartbeat == now
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  signer_present && not_expired && renewed
}

fn validate_prune(datum: RegistryDatum, tx: Transaction) -> Bool {
  expect Membership(member) = datum
  expect Finite(now) = tx.validity_range.lower_bound.bound_type
  member.active_until < now
}

fn validate_update_config(datum: RegistryDatum, tx: Transaction) -> Bool {
  expect Config(config) = datum
  list.has(tx.extra_signatories, config.admin_pkh)
}
