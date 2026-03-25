/// Shared types for The AI Assembly governance system on Vector UTXO

/// Risk tier for treasury spending proposals
pub type RiskTier {
  Routine
  Significant
  Major
  Constitutional
}

/// Kind of governance proposal
pub type ProposalKind {
  ConfigChange
  Dissolution
  IntentBundle
}

/// Origin of a proposal
pub type ProposalOrigin {
  Council
  Petition
}

/// Current status of a proposal
pub type ProposalStatus {
  Deliberation
  Voting
  Timelock
  Executed
  Defeated
  Cancelled
}

/// Vote choice
pub type VoteChoice {
  Against
  For
  Abstain
}

/// Thread kind in the forum
pub type ThreadKind {
  Discussion
  Proposal
  PetitionThread
}

/// Configuration update for governance proposals
pub type ConfigUpdate {
  key: ByteArray,
  value: Int,
}
