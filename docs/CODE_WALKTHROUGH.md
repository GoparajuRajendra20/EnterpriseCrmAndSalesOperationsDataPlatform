# Code walkthrough

This guide follows a source record through the application and explains the main design decisions. Comments in the source focus on these decisions rather than narrating obvious assignments.

## 1. Generate related records

`generate.py` creates campaigns and partners before their leads and sales so foreign keys refer to real source entities. Separate seeded random generators make the sample reproducible. Random-call order is preserved because changing it changes the recorded dataset and model results.

Booking errors, unpaid accruals, a replayed sale and an invalid amount are deliberate fixtures. They let the demo exercise success and failure paths instead of showing only clean data.

## 2. Validate before calculating reports

`pipeline.py` separates ingestion, source validation, sale cleaning, business calculations and publication. Each named function handles one stage. Broken dimension keys fail the batch; invalid financial rows are preserved in quarantine. An identical replay can be collapsed, while two different records sharing a sale ID are ambiguous and stop the run.

Financial source columns use Spark decimal types. Partner commission variance compares booked and expected accruals; paid commission is a separate value. Representative accelerators apply only to revenue above quota. Customer onboarding is aggregated before ticket metrics are joined so customers with more tickets do not distort onboarding averages.

## 3. Separate HTTP from business rules

`server.py` owns routing, authentication, request limits, response codes and persistence. `workflows.py` owns lead validation, approval eligibility, statement fingerprints and simulated settlement rules. Those rules can be tested without opening a server.

A file lock coordinates threads within the single API process. Atomic JSON replacement avoids partially written state. Multiple API processes would require shared transactional persistence; the current design does not claim that capability.

## 4. Enforce access on the server

`auth.py` resolves an active identity from its hashed token, checks an explicit role allowlist and scopes partner rows. Hiding a button would not protect the underlying endpoint, so authorization happens before report access or state changes.

The database-backed report path sets role/partner context for the current transaction only. The CSV-backed path applies the same partner filter before the row limit. Tokens and request bodies stay out of access-decision logs.

## 5. Prevent duplicate simulated settlements

Approval starts with expected commission minus existing source payments. Previous simulated settlements are then subtracted. Otherwise, refreshing a cumulative report could offer the same amount again.

An approval records a fingerprint of the reviewed statement. Payout requires the same statement, a different reviewer and an outstanding approved state. The event updates only the local simulation ledger; no payment provider is invoked.

## 6. Evaluate a future period

`train.py` builds categorical encoders and logistic regression as one Spark pipeline. Fitting the encoders on training data avoids learning category frequencies from the holdout. A temporal split and observation gap separate training labels from the evaluated period. Outcome and post-sale revenue are excluded from the predictors.

The model, scores and metrics are saved together. Synthetic data limits what the AUC demonstrates; it verifies the modeling workflow rather than real customer behavior.

## 7. Keep operational entry points explicit

Cloud deployment, database initialization, model training and workbook generation run through `main()` guards. Importing those modules to inspect or reuse their functions does not provision infrastructure or regenerate files.

Cloud deployment remains on hold. PostgreSQL runtime integration and native Tableau rendering still need their separately documented verification. Refactoring does not change those evidence boundaries.
