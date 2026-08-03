Feature: Evidence-backed product definition
  As a product manager
  I want an auditable AI research workflow
  So that product recommendations can be challenged and reproduced

  Scenario: Complete an eufy research project
    Given a confirmed research brief for North American renters
    When the research workflow gathers and validates evidence
    And a human promotes one candidate concept
    Then the final proposal cites valid evidence identifiers
    And rejected concepts retain their rejection reasons
    And unknown questions remain visible

  Scenario: Block an unsupported factual claim
    Given a factual claim with no valid supporting evidence
    When the claim gate evaluates the final proposal
    Then the claim is excluded from the proposal
    And the exclusion is recorded in the project trace

  Scenario: Resume after a collection failure
    Given an evidence source fails during collection
    When an operator retries from the saved checkpoint
    Then completed unaffected stages are not repeated
    And the failed source remains visible in coverage metrics
