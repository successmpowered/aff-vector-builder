/// Treasury Validator - Fund custody and governance-authorized spending
///
/// EVM equivalent: Treasury.sol

use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/interval.{Finite}
use cardano/address.{VerificationKey}
use cardano/assets
use cardano/transaction.{OutputReference, Transaction, InlineDatum}

pub type TreasuryConfig {
  governance_script_hash: ByteArray,
  admin_pkh: VerificationKeyHash,
  major_spend_cooldown: Int,
  last_major_spend_at: Int,
}

pub type TreasuryDatum {
  TConfig(TreasuryConfig)
  TFunds
}

pub type TreasuryAction {
  Receive
  ExecuteTransfer {
    recipient_pkh: VerificationKeyHash,
    amount: Int,
  }
  UpdateTreasuryConfig
}

validator treasury {
  spend(
    datum_opt: Option<TreasuryDatum>,
    redeemer: TreasuryAction,
    _own_ref: OutputReference,
    tx: Transaction,
  ) {
    expect Some(datum) = datum_opt
    when redeemer is {
      Receive -> True
      ExecuteTransfer { recipient_pkh, amount } ->
        validate_transfer(datum, tx, recipient_pkh, amount)
      UpdateTreasuryConfig -> validate_update_treasury(datum, tx)
    }
  }

  else(_) {
    fail
  }
}

fn validate_transfer(
  datum: TreasuryDatum,
  tx: Transaction,
  recipient_pkh: VerificationKeyHash,
  amount: Int,
) -> Bool {
  expect TConfig(config) = datum

  // Recipient must receive the specified amount
  let recipient_paid =
    list.any(
      tx.outputs,
      fn(output) {
        when output.address.payment_credential is {
          VerificationKey(pkh) ->
            pkh == recipient_pkh && assets.lovelace_of(output.value) >= amount
          _ -> False
        }
      },
    )

  // Config must be reproduced
  let config_reproduced =
    list.any(
      tx.outputs,
      fn(output) {
        when output.datum is {
          InlineDatum(d) -> {
            expect out_datum: TreasuryDatum = d
            when out_datum is {
              TConfig(new_config) ->
                new_config.governance_script_hash == config.governance_script_hash && new_config.admin_pkh == config.admin_pkh
              _ -> False
            }
          }
          _ -> False
        }
      },
    )

  recipient_paid && config_reproduced
}

fn validate_update_treasury(datum: TreasuryDatum, tx: Transaction) -> Bool {
  expect TConfig(config) = datum
  list.has(tx.extra_signatories, config.admin_pkh)
}
