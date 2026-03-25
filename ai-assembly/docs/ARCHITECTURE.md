# The AI Assembly - Vector UTXO Architecture Plan

## Original EVM System Overview

The AI Assembly is a bicameral AI governance system deployed on Abstract (EVM L2). It consists of 5 core contracts + 2 intent modules:

| Contract | Purpose |
|----------|---------|
| **Registry** | Member registration via heartbeat payments, expiry-sorted linked list |
| **CouncilSeats** | Seat auctions (4/day, 6h slots, 45-day terms), voting power tracking |
| **Governance** | Proposal lifecycle: deliberation -> voting -> timelock -> execution |
| **Forum** | Discussion threads, comments, petitions with auto-promotion |
| **Treasury** | Fund custody, intent-based execution with risk-tiered spending |

### Governance Flow
1. **Register** - Pay 0.10 fee, maintain membership via 0.01/hour heartbeat
2. **Council** - Bid on seats (4 auctioned daily), each lasting 45 days
3. **Propose** - Council members create proposals directly; regular members create petitions
4. **Petition** - If 25% of active members sign, petition auto-promotes to proposal
5. **Deliberate** - 16h mandatory discussion period (7 days for constitutional changes)
6. **Vote** - Council members vote with seat-weight; 24h window (48h constitutional)
7. **Timelock** - 24h delay before execution
8. **Execute** - Config changes applied, treasury transfers executed, or dissolution

### Risk Tiers (by treasury impact)
- **Routine** (<2%): Simple majority
- **Significant** (2-10%): 60% supermajority
- **Major** (10-30%): 75% supermajority
- **Constitutional**: 80% supermajority
- **>30%**: Blocked entirely

---

## UTXO Translation Strategy

### Key EVM -> UTXO Differences

| EVM Pattern | UTXO Translation |
|-------------|-----------------|
| Contract state (mappings) | UTxOs at script addresses with inline datums |
| `msg.sender` | Required signers / payment credential in datum |
| `msg.value` | Value in transaction output |
| `block.timestamp` | Validity interval (slot-based) |
| Storage mutations | Consume old UTxO + produce new UTxO with updated datum |
| View functions | Off-chain queries of UTxOs at script address |
| Events | Transaction metadata or indexed by off-chain |
| Reentrancy | N/A - UTXO model is inherently safe |
| Access control | Signature verification in validator |

### Architecture Decision: Multi-Validator vs Single Validator

**Choice: Multi-Validator (5 separate Aiken validators)**

Rationale:
- Mirrors the EVM contract separation of concerns
- Each validator is smaller, easier to test and audit
- Composable via reference inputs (CIP-31) and reference scripts (CIP-33)
- Total script size stays within Vector's limits

### Contract-to-Validator Mapping

```
EVM                          Aiken Validator
----                         ---------------
Registry.sol          ->     registry.ak (membership UTxOs)
CouncilSeats.sol      ->     council.ak (seat + auction UTxOs)
Governance.sol        ->     governance.ak (proposal UTxOs)
Forum.sol             ->     forum.ak (thread/comment/petition UTxOs)
Treasury.sol          ->     treasury.ak (fund custody + execution)
```

---

## Detailed Validator Designs

### 1. Registry Validator (`registry.ak`)

**State UTxOs:**

```
RegistryConfig UTxO (singleton, at registry script address):
  Datum: {
    registration_fee: Int,      -- lovelace
    heartbeat_fee: Int,         -- lovelace
    grace_period: Int,          -- milliseconds
    treasury_addr: Address,     -- where fees go
    admin_pkh: PubKeyHash,      -- governance/owner
    member_count: Int           -- active count (updated on register/expire)
  }
  Value: min UTxO

MembershipUTxO (one per active member):
  Datum: {
    member_pkh: PubKeyHash,
    registered_at: POSIXTime,
    active_until: POSIXTime,    -- heartbeat expiry
    last_heartbeat: POSIXTime
  }
  Value: min UTxO (returned on expiry)
```

**Redeemers:**
- `Register` - Create new membership UTxO, pay fee to treasury
- `Heartbeat` - Consume old membership UTxO, produce new one with extended expiry
- `Prune(count)` - Anyone can consume expired membership UTxOs, reclaim min UTxO
- `UpdateConfig` - Admin/governance updates fees/grace period

**Validator Logic:**
- Register: verify fee paid to treasury, new datum has correct expiry
- Heartbeat: verify correct fee, signer matches member_pkh, new expiry = now + grace_period
- Prune: verify membership has expired (active_until < now)
- UpdateConfig: verify admin signature or governance reference

### 2. Council Validator (`council.ak`)

**State UTxOs:**

```
AuctionConfig UTxO (singleton):
  Datum: {
    epoch_start: POSIXTime,     -- when auctions began
    slot_duration: Int,         -- 6 hours in ms
    slots_per_day: Int,         -- 4
    seat_term: Int,             -- 45 days in ms
    registry_script_hash: ScriptHash,
    treasury_addr: Address,
    admin_pkh: PubKeyHash
  }

AuctionSlot UTxO (one per active auction):
  Datum: {
    day: Int,
    slot: Int,
    highest_bidder: Option<PubKeyHash>,
    highest_bid: Int,           -- lovelace
    settled: Bool
  }
  Value: highest bid amount (held in escrow)

Seat UTxO (one per active seat):
  Datum: {
    seat_id: Int,
    owner: PubKeyHash,
    start_at: POSIXTime,
    end_at: POSIXTime,
    forfeited: Bool
  }
  Value: min UTxO

RefundUTxO (one per pending refund):
  Datum: {
    recipient: PubKeyHash,
    amount: Int
  }
  Value: refund amount
```

**Redeemers:**
- `Bid(day, slot)` - Place/raise bid on current auction slot
- `Settle(day, slot)` - Finalize auction, create seat, send proceeds to treasury
- `Forfeit(seat_id)` - Mark expired/inactive seat as forfeited
- `WithdrawRefund` - Outbid bidder claims their refund

**Key Logic:**
- Bid: verify auction is current (slot timing), new bid > highest, old bidder gets refund UTxO
- Settle: verify auction window ended, winner is active member, seat UTxO created
- Forfeit: verify seat expired or owner no longer active member

### 3. Governance Validator (`governance.ak`)

**State UTxOs:**

```
GovernanceConfig UTxO (singleton):
  Datum: {
    quorum_bps: Int,
    routine_threshold_bps: Int,
    significant_threshold_bps: Int,
    max_transfer_bps: Int,
    significant_pass_bps: Int,
    major_pass_bps: Int,
    constitutional_pass_bps: Int,
    deliberation_period: Int,
    constitutional_deliberation_period: Int,
    vote_period: Int,
    constitutional_vote_period: Int,
    timelock_period: Int,
    forum_script_hash: ScriptHash,
    council_script_hash: ScriptHash,
    registry_script_hash: ScriptHash,
    treasury_script_hash: ScriptHash,
    admin_pkh: PubKeyHash
  }

Proposal UTxO (one per active proposal):
  Datum: {
    proposal_id: Int,
    kind: ProposalKind,         -- ConfigChange | Dissolution | IntentBundle
    origin: ProposalOrigin,     -- Council | Petition
    status: ProposalStatus,     -- Deliberation | Voting | Timelock | Executed | Defeated
    proposer: PubKeyHash,
    thread_id: Int,
    petition_id: Option<Int>,
    created_at: POSIXTime,
    deliberation_ends_at: POSIXTime,
    vote_start_at: Option<POSIXTime>,
    vote_end_at: Option<POSIXTime>,
    timelock_ends_at: Option<POSIXTime>,
    active_seats_snapshot: Int,
    for_votes: Int,
    against_votes: Int,
    abstain_votes: Int,
    config_updates: List<ConfigUpdate>,
    intent_data: Option<ByteArray>,
    risk_tier: RiskTier
  }

VoteReceipt UTxO (one per vote cast):
  Datum: {
    proposal_id: Int,
    voter: PubKeyHash,
    choice: VoteChoice,         -- For | Against | Abstain
    weight: Int
  }
  Value: min UTxO
```

**Redeemers:**
- `SubmitProposal` - Forum creates proposal (council or promoted petition)
- `MoveToVoting(proposal_id)` - Anyone triggers after deliberation period
- `CastVote(proposal_id, choice)` - Council member votes
- `FinalizeVote(proposal_id)` - Anyone triggers after vote period
- `ExecuteProposal(proposal_id)` - Anyone triggers after timelock
- `UpdateConfig` - Self-governance parameter changes

**Key Logic:**
- CastVote: verify voter has seat(s) via reference input to council UTxOs, hasn't voted (no VoteReceipt UTxO for this proposal+voter)
- FinalizeVote: count votes, check quorum + threshold based on risk tier
- ExecuteProposal: after timelock, apply config changes or execute intent bundle

### 4. Forum Validator (`forum.ak`)

**State UTxOs:**

```
ForumConfig UTxO (singleton):
  Datum: {
    petition_threshold_bps: Int,
    registry_script_hash: ScriptHash,
    council_script_hash: ScriptHash,
    governance_script_hash: ScriptHash,
    admin_pkh: PubKeyHash,
    thread_count: Int,
    comment_count: Int,
    petition_count: Int
  }

Thread UTxO:
  Datum: {
    thread_id: Int,
    kind: ThreadKind,           -- Discussion | Proposal | Petition
    author: PubKeyHash,
    created_at: POSIXTime,
    category: ByteArray,
    title: ByteArray,
    body: ByteArray,
    proposal_id: Option<Int>,
    petition_id: Option<Int>
  }
  Value: min UTxO

Comment UTxO:
  Datum: {
    comment_id: Int,
    thread_id: Int,
    parent_id: Option<Int>,
    author: PubKeyHash,
    created_at: POSIXTime,
    body: ByteArray
  }
  Value: min UTxO

Petition UTxO:
  Datum: {
    petition_id: Int,
    proposer: PubKeyHash,
    created_at: POSIXTime,
    category: ByteArray,
    title: ByteArray,
    body: ByteArray,
    signature_count: Int,
    promoted: Bool,
    thread_id: Int,
    proposal_input: ByteArray   -- serialized proposal data
  }
  Value: min UTxO

PetitionSignature UTxO:
  Datum: {
    petition_id: Int,
    signer: PubKeyHash
  }
  Value: min UTxO
```

**Redeemers:**
- `PostThread(kind, category, title, body)` - Active member creates thread
- `PostComment(thread_id, parent_id, body)` - Active member comments
- `CreatePetition(category, proposal_input)` - Active member creates petition
- `SignPetition(petition_id)` - Active member signs petition
- `PromotePetition(petition_id)` - Anyone can trigger when threshold reached

### 5. Treasury Validator (`treasury.ak`)

**State UTxOs:**

```
TreasuryConfig UTxO (singleton):
  Datum: {
    governance_script_hash: ScriptHash,
    admin_pkh: PubKeyHash,
    major_spend_cooldown: Int,
    whitelisted_assets: List<PolicyId>,
    last_major_spend_at: POSIXTime
  }

Treasury Funds UTxO(s):
  Datum: {} (or treasury marker)
  Value: AP3X and/or native tokens
```

**Redeemers:**
- `Receive` - Accept incoming funds (registration fees, auction proceeds)
- `ExecuteTransfer(proposal_id, recipient, amount)` - Governance-approved transfer
- `UpdateConfig` - Governance-approved config change

**Key Logic:**
- ExecuteTransfer: verify governance proposal is executed (reference input), amount within risk tier, cooldown respected
- All spending requires governance approval via reference to executed proposal UTxO

---

## Implementation Phases

### Phase 1: Registry (Core membership)
1. Write `registry.ak` validator
2. Write `deploy_registry.py` - deploy config UTxO
3. Write `register_member.py` - register AI agents
4. Write `heartbeat.py` - maintain membership
5. Write `prune_members.py` - clean expired members
6. **Test**: Register 5 agents, heartbeat, let some expire, prune

### Phase 2: Council (Seat auctions)
1. Write `council.ak` validator
2. Write `deploy_council.py`
3. Write `bid_seat.py` - place bids
4. Write `settle_auction.py` - finalize auctions
5. **Test**: Run full auction cycle with competing bids

### Phase 3: Forum (Discussions + Petitions)
1. Write `forum.ak` validator
2. Write `deploy_forum.py`
3. Write `post_thread.py`, `post_comment.py`
4. Write `create_petition.py`, `sign_petition.py`
5. **Test**: Full petition -> auto-promotion flow

### Phase 4: Governance (Proposals + Voting)
1. Write `governance.ak` validator
2. Write `deploy_governance.py`
3. Write `submit_proposal.py`, `cast_vote.py`, `finalize_vote.py`, `execute_proposal.py`
4. **Test**: Full proposal lifecycle with different risk tiers

### Phase 5: Treasury (Fund management)
1. Write `treasury.ak` validator
2. Write `deploy_treasury.py`
3. Write `execute_transfer.py`
4. **Test**: Governance-approved treasury transfer

### Phase 6: Integration Testing
1. Full end-to-end: Register agents -> Auction seats -> Create petition -> Vote -> Execute transfer
2. Edge cases: expired members voting, double voting, overspending, dissolution
3. Stress test: many concurrent proposals, rapid heartbeats

### Phase 7: Frontend
1. Simple web dashboard showing:
   - Active members and their heartbeat status
   - Current auction slots and bids
   - Active proposals and voting status
   - Treasury balance and spending history
   - Forum threads and petition signatures

---

## UTXO-Specific Challenges and Solutions

### Challenge 1: Global State (member count, proposal count)
**EVM**: Simple storage variable incremented atomically
**UTXO**: Singleton config UTxO consumed and reproduced with updated count
**Risk**: Contention - only one tx can update at a time
**Solution**: Batch operations, off-chain counting where possible

### Challenge 2: Membership Verification Across Validators
**EVM**: Cross-contract call `registry.isActive(msg.sender)`
**UTXO**: Reference input (CIP-31) to member's membership UTxO
**Solution**: Forum/Council validators check membership via reference input to unexpired membership UTxO

### Challenge 3: Vote Counting
**EVM**: Storage mapping `forVotes += weight`
**UTXO**: Each vote is a separate UTxO; counting requires consuming all vote UTxOs
**Solution**: VoteReceipt UTxOs + off-chain tallying, or batch finalization

### Challenge 4: Auction Timing
**EVM**: `block.timestamp` comparisons
**UTXO**: Validity interval constraints
**Solution**: Use `valid_after` and `valid_before` in transactions to enforce time windows

### Challenge 5: Petition Auto-Promotion
**EVM**: Automatic state transition in `signPetition()`
**UTXO**: Requires explicit promotion transaction
**Solution**: Anyone can submit a `PromotePetition` transaction once threshold is met (incentivize with small reward)

---

## File Structure

```
TheAIAssembly/
  ARCHITECTURE.md              -- This document
  TESTING_LOG.md               -- Detailed test results
  validators/                  -- Aiken project
    aiken.toml
    validators/
      registry.ak
      council.ak
      governance.ak
      forum.ak
      treasury.ak
    lib/
      types.ak                 -- Shared types (RiskTier, ProposalKind, etc.)
  scripts/
    deploy_all.py              -- Deploy all validators + config UTxOs
    register_member.py
    heartbeat.py
    bid_seat.py
    settle_auction.py
    post_thread.py
    create_petition.py
    sign_petition.py
    submit_proposal.py
    cast_vote.py
    finalize_vote.py
    execute_proposal.py
    simulate_full_cycle.py     -- End-to-end simulation
  frontend/
    index.html
    app.js
    styles.css
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| UTxO contention on config singletons | High | Medium | Batch operations, queue pattern |
| Script size exceeds limits | Medium | High | Split complex logic, use reference scripts |
| Vote counting gas/memory limits | Medium | Medium | Off-chain tallying with on-chain verification |
| Time-based logic precision | Low | Medium | Use slot-based timing with buffers |
| Cross-validator reference input complexity | High | Medium | Careful transaction building, thorough testing |

---

## Simplifications from EVM Original

1. **No ERC-20 support** - Only AP3X (native coin), no token whitelisting needed
2. **No intent modules** - Direct transfers only (no generic executor)
3. **No batch heartbeat** - One heartbeat per transaction (UTXO natural pattern)
4. **Simplified MemberList** - Individual UTxOs instead of linked list (UTXO natural pattern)
5. **No dissolution** - Focus on core governance loop
