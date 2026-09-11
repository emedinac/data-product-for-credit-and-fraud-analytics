# Customer Data Product — Financial Services

## 1. Business Context

We are **PayFlow Financial Services**, a financial services company that provides payment and consumer credit products.

Our business currently operates several systems that contain information about our customers, accounts, transactions, fraud events, and customer interactions.

As our business has grown, different teams have started creating their own datasets and definitions of what a "customer" is.

This has created several problems:

- Different teams calculate customer metrics differently.
- Fraud models use different versions of customer behavior metrics.
- Portfolio analysts don't always agree on balances, utilization, or customer status.
- Some datasets are stale or incomplete.
- Data quality problems are often discovered only after the data has been consumed.
- Source-system changes can unexpectedly break downstream processes.
- It is difficult to determine where a particular customer attribute came from.
- There is no clear ownership for many datasets and fields.
- Consumers don't have clear guarantees regarding freshness, availability, or quality.
- Machine-learning teams have difficulty reproducing the data used for previous model training.

We want to address these problems by creating a **Customer Data Product** that becomes a trusted and reusable source of customer information for our analytics and machine-learning teams.

---

# 2. Customer Requirement

We need a **Customer Data Product** that provides reliable customer-level information to multiple internal consumers.

The Customer Data Product must not be considered only as a data transformation process.

It must provide a governed and reusable interface for consumers of customer data.

The product must have clearly defined:

- Data contracts
- Schemas
- Data definitions and semantics
- Ownership
- Data-quality expectations
- Service-level agreements
- Access policies
- Data lineage
- Versioning
- Monitoring
- Consumer access mechanisms

The Customer Data Product will initially support three main consumer groups:

1. Analytics
2. Fraud Detection / Machine Learning
3. Portfolio Analytics

---

# 3. Customer Data Sources

The company currently has information distributed across several operational systems.

## 3.1 Customer System

The customer system contains information about customers.

The available information includes:

```text
customer_id
first_name
last_name
date_of_birth
country
city
registration_date
customer_status
customer_type
```

Possible customer statuses include:

```text
ACTIVE
INACTIVE
BLOCKED
CLOSED
```

Possible customer types include:

```text
INDIVIDUAL
PREMIUM
BUSINESS
```

---

## 3.2 Account System

Customers can have one or more financial accounts.

The account system contains:

```text
account_id
customer_id
account_type
opening_date
closing_date
credit_limit
current_balance
account_status
```

Possible account types include:

```text
CREDIT_CARD
PERSONAL_LOAN
PAYMENT_ACCOUNT
```

---

## 3.3 Transaction System

The transaction system contains financial transactions performed by customers.

The available information includes:

```text
transaction_id
customer_id
account_id
timestamp
amount
currency
transaction_type
merchant_id
merchant_category
country
status
```

Possible transaction types include:

```text
PURCHASE
WITHDRAWAL
TRANSFER
PAYMENT
REFUND
```

Possible transaction statuses include:

```text
APPROVED
DECLINED
REVERSED
```

---

## 3.4 Fraud Event System

The fraud system contains events related to potentially fraudulent activity.

The available information includes:

```text
event_id
transaction_id
customer_id
event_timestamp
event_type
severity
confirmed_fraud
```

Possible event types include:

```text
SUSPICIOUS_TRANSACTION
ACCOUNT_TAKEOVER
CARD_STOLEN
IDENTITY_RISK
CHARGEBACK
```

---

## 3.5 Customer Interaction System

The company also records interactions between customers and our service channels.

The available information includes:

```text
interaction_id
customer_id
timestamp
channel
interaction_type
resolution
```

Possible channels include:

```text
APP
WEB
PHONE
EMAIL
BRANCH
```

---

# 4. Data Volume

The initial environment should represent approximately the following scale:

```text
Customers: ...
Accounts: ...
Transactions: ...
Fraud events: ...
Interactions: ...
```

The numbers are not known yet, but the customer expect 10M data points. they are representative and expected. The data may be generated synthetically for the purposes of this project. The generated data must preserve the relationships between the different business entities.

For example:

- A transaction must belong to an account.
- An account must belong to a customer.
- A fraud event may reference a transaction and customer.
- An interaction must reference a customer.

---

# 5. Data Quality

The operational systems are not perfect.

The Customer Data Product must account for realistic data-quality issues originating from our source systems.

Examples of issues that may occur include:

### Missing data

Some records may contain missing values.

Examples include:

```text
city
merchant_id
closing_date
merchant_category
```

### Duplicate records

The same transaction or event may occasionally be delivered more than once.

### Invalid values

Source systems may contain invalid or unexpected values.

For example:

```text
customer_status = "ACTVE"
```

or values that violate expected business rules.

### Late-arriving data

A transaction may occur on one date but arrive in the data platform later.

For example:

```text
Transaction occurred:
2026-01-10

Transaction received:
2026-01-12
```

### Changing information

Customer and account information can change over time.

For example:

```text
Customer status:

ACTIVE → BLOCKED
```

or:

```text
Credit limit:

5,000 → 10,000
```

The Customer Data Product must provide consumers with appropriate and understandable representations of these changes.

---

# 6. Analytics Consumer

Our Analytics team needs a trusted source of customer information.

They need to answer questions such as:

- How many active customers do we have?
- How many customers increased their transaction activity during the last three months?
- What is the average transaction amount by customer segment?
- How many customers have outstanding balances?
- What percentage of customers are highly utilized?
- How is customer activity distributed across countries?
- How has the customer portfolio changed over time?

The Analytics team should not need to independently reconstruct customer-level metrics from multiple operational sources.

---

# 7. Fraud Detection Consumer

Our Fraud Detection and Machine Learning team needs customer-level information as input to fraud-related models.

Potential customer attributes include:

```text
transaction_count_7d
transaction_count_30d
transaction_count_90d
transaction_amount_7d
transaction_amount_30d
average_transaction_amount
declined_transaction_count
decline_rate
distinct_merchant_count
distinct_country_count
fraud_event_count
confirmed_fraud_count
days_since_last_transaction
customer_tenure
account_count
```

These are examples of the type of information the team may require.

The Fraud team needs consistent definitions for these attributes.

For example, if the Customer Data Product provides:

```text
transaction_count_30d
```

the team must be able to understand exactly:

- Which transactions are included?
- What time period is used?
- Are declined transactions included?
- Are reversed transactions included?
- How are refunds handled?
- What happens when data is missing?

The Fraud team also requires historical data that can support model training and evaluation.

Data used for machine-learning models must be suitable for **point-in-time analysis** and must avoid using information that would not have been available at the time a prediction was made.

---

# 8. Portfolio Analytics Consumer

Our Portfolio Analytics team uses customer information to understand the financial portfolio.

They need information such as:

```text
customer_id
customer_status
customer_since
account_count
total_credit_limit
total_balance
credit_utilization
transaction_activity
payment_activity
delinquency_indicators
customer_segment
```

The Portfolio team needs to analyze customer behavior over time.

Examples include:

- How does customer utilization change over time?
- Which customer segments have the highest balances?
- How many customers are increasing their utilization?
- How is the portfolio distributed by customer segment?
- How many customers have become inactive?
- How does transaction activity change before and after a customer changes status?

---

# 9. Customer-Level Data Product

The Customer Data Product should provide a customer-level representation of information relevant to our consumers.

Potential attributes may include:

```text
customer_id
customer_status
customer_type
customer_since
country
customer_age_band

transaction_count_30d
transaction_count_90d
transaction_amount_30d
transaction_amount_90d
average_transaction_amount_30d
declined_transaction_count_30d
distinct_merchants_30d

fraud_event_count_90d
confirmed_fraud_count

account_count
total_credit_limit
total_balance
credit_utilization

days_since_last_transaction
portfolio_segment
```

The final product definition must establish which information is appropriate for the Customer Data Product.

The product must have a clearly defined **grain**.

Consumers must be able to determine exactly what one record represents.

---

# 10. Data Contract

Consumers require a formal contract describing the Customer Data Product.

The contract must define the expected structure and behavior of the product.

It must establish information such as:

- Field names
- Data types
- Required fields
- Nullable fields
- Allowed values
- Business definitions
- Units of measurement
- Time semantics
- Update behavior
- Expected freshness
- Compatibility expectations

Consumers must be able to understand what each field means without inspecting the implementation that produces it.

For example, the meaning of:

```text
credit_utilization
```

must be explicitly defined.

The behavior of the metric must also be defined for situations such as:

- Zero credit limit
- Closed accounts
- Missing balances
- Multiple accounts
- Historical records

---

# 11. Data Semantics

We need consistent definitions for important business concepts.

Examples include:

### Active Customer

The company must have a clear definition of what constitutes an active customer.

### Customer Tenure

The product must define how customer tenure is calculated.

### Transaction Count

The product must define which transaction statuses and types are included.

### Balance

The product must define what constitutes a customer's balance.

### Credit Utilization

The product must define how utilization is calculated.

### Fraud Event

The product must define what qualifies as a fraud event.

These definitions must be documented and consistent across consumers.

---

# 12. Data Quality Requirements

The Customer Data Product must have measurable quality expectations.

We need to be able to evaluate characteristics such as:

- Completeness
- Uniqueness
- Validity
- Consistency
- Referential integrity
- Accuracy
- Freshness

Examples of business expectations include:

- Customer identifiers must be unique at the defined product grain.
- Customer references must correspond to known customers.
- Financial amounts must follow defined business rules.
- Required fields must meet defined completeness thresholds.
- The product must not contain unexpected schema changes.
- Data must be delivered within the agreed freshness window.

The specific quality rules and thresholds must be formally defined for the product.

---

# 13. SLA Requirements

The Customer Data Product must have explicit service-level expectations.

The business requires clear guarantees around:

### Freshness

Customer information must be available within an agreed period after the source data becomes available.

### Availability

Consumers must have reliable access to the product.

### Data Quality

The product must meet agreed quality thresholds.

### Recovery

In the event of a failure, the company needs an agreed recovery expectation.

The SLA must be measurable so that the company can determine whether the product is meeting its commitments.

---

# 14. Ownership

The Customer Data Product must have clearly defined ownership.

The company needs to know:

- Who is responsible for the product?
- Who approves changes?
- Who responds to data-quality incidents?
- Who maintains the data contract?
- Who communicates breaking changes?
- Who is responsible for SLA compliance?

The ownership model must be visible to consumers.

---

# 15. Data Lineage

Consumers need to understand where customer information originates.

For important attributes, we need to be able to determine:

- Which source system produced the information?
- Which source fields were used?
- What transformations were applied?
- Which version of the product contains the information?
- Which downstream consumers use the information?

For example, a consumer should be able to understand the origin of:

```text
customer_status
total_balance
transaction_count_30d
credit_utilization
fraud_event_count_90d
```

---

# 16. Access Policies

Customer information is sensitive financial data.

Access to the Customer Data Product must follow appropriate policies.

Different consumers may require different levels of access.

For example:

### Analytics

May require customer-level financial metrics but may not require personally identifiable information.

### Fraud / ML

May require behavioral and historical attributes.

### Data Engineering

May require broader technical access for operational purposes.

The company needs clear rules defining which consumers can access which information.

---

# 17. Versioning and Change Management

The Customer Data Product will evolve.

Fields may be:

- Added
- Removed
- Renamed
- Reinterpreted
- Deprecated

Source systems may also change independently.

For example, the transaction system may change:

```text
merchant_category
```

to:

```text
merchant_category_code
```

The company needs a controlled process for handling changes to the Customer Data Product.

Consumers must be able to understand:

- Which version they are consuming.
- Which changes are backward compatible.
- Which changes are breaking.
- When a version will be deprecated.
- How consumers migrate to a new version.

---

# 18. Historical Data

The company requires historical customer information.

A consumer may ask:

> "What information did we have about this customer on January 31?"

The answer should represent the appropriate state of the data at that point in time rather than simply returning the customer's current state.

Historical information is particularly important for:

- Portfolio analysis
- Fraud analysis
- Machine-learning training
- Model evaluation
- Regulatory and business analysis

---

# 19. Reproducibility

Our Machine Learning team needs to reproduce historical datasets.

For example:

> "We trained Fraud Model 3.2 using customer information available on June 30."

Six months later, the team should be able to identify and reproduce the relevant historical customer data.

The product must therefore provide sufficient information to understand:

- Which data version was used.
- Which product version was used.
- Which definitions were active.
- Which historical state was represented.
- When the data was produced.

---

# 20. Monitoring and Operational Visibility

The company needs visibility into the health of the Customer Data Product.

We need to know when:

- Data processing fails.
- Data arrives late.
- Data volumes change unexpectedly.
- Required fields contain excessive nulls.
- Duplicate records increase.
- Referential integrity fails.
- Business rules fail.
- A source schema changes.
- The product violates its SLA.
- Consumers experience a service disruption.

Operational issues must be detectable and traceable.

---

# 21. Consumer Access

The Customer Data Product must provide a clearly defined way for approved consumers to access the data.

Consumers should not need to understand the internal implementation of the product in order to use it.

The access mechanism must provide:

- A documented interface
- Defined schema
- Defined semantics
- Version information
- Appropriate access controls
- Information about freshness and quality

---

# 22. Synthetic Data

For the initial implementation, the company will provide no real customer data.

The development environment must therefore use synthetic financial data.

The synthetic environment should represent approximately:

```text
100,000 customers
150,000 accounts
2,000,000 transactions
20,000 fraud events
500,000 customer interactions
```

The generated data should contain realistic relationships between entities and should represent normal financial activity.

The environment should also be capable of representing realistic operational problems such as:

- Missing values
- Duplicate records
- Invalid values
- Late-arriving records
- Changing customer attributes
- Changing account attributes
- Source-system changes
- Abnormal transaction activity
- Fraud spikes

No real customer personally identifiable information should be used.

---

# 23. Business Scenarios

The Customer Data Product must support scenarios such as:

### Scenario 1 — Customer Analytics

The Analytics team wants to identify all active customers and analyze their recent transaction behavior.

### Scenario 2 — Portfolio Analysis

The Portfolio team wants to analyze customer balances, credit limits, and utilization by customer segment.

### Scenario 3 — Fraud Analysis

The Fraud team wants to analyze customer transaction behavior and historical fraud indicators.

### Scenario 4 — ML Training

The ML team wants to construct a historical dataset for training a fraud-related model.

### Scenario 5 — Point-in-Time Analysis

An analyst wants to understand what was known about a customer at a specific historical date.

### Scenario 6 — Source-System Change

The transaction source changes its schema.

Existing consumers should not unexpectedly lose access to the Customer Data Product.

### Scenario 7 — Data Quality Incident

The transaction source sends an abnormal number of duplicate records.

The company needs to detect and understand the impact on the Customer Data Product.

### Scenario 8 — SLA Incident

The Customer Data Product is not available within the agreed delivery window.

The company needs to determine what happened and whether the SLA was violated.

---

# 24. Definition of Success

The Customer Data Product will be considered successful when our Analytics, Fraud, and Portfolio teams can rely on it as a trusted source of customer information.

As the customer, we should be able to answer the following questions:

### Trust

> Can we trust this data?

### Ownership

> Who is responsible for this data?

### Meaning

> What exactly does this field mean?

### Quality

> How do we know whether the data is correct and complete?

### Freshness

> How recent is this information?

### SLA

> What level of service are we guaranteed?

### Lineage

> Where did this information come from?

### Security

> Who is allowed to access it?

### Versioning

> Which version am I using?

### Change management

> What happens when the product changes?

### History

> What did we know about the customer at a previous point in time?

### Reproducibility

> Can the ML team reproduce the data used to train a previous model?

### Operations

> How do we know when something goes wrong?

---

# 25. Final Business Requirement

We are not asking for a collection of tables or a one-time data pipeline.

We need a **Customer Data Product** that can become a trusted internal data interface for our company.

The product must allow multiple teams to consume customer information with clear expectations around:

```text
Data
Contracts
Semantics
Quality
Ownership
Security
Freshness
Availability
Lineage
Versioning
History
Monitoring
Access
```

The Customer Data Product should be capable of evolving as our business, source systems, analytics requirements, and machine-learning use cases evolve.

Our expectation is that consumers should be able to use the product without needing to understand how the underlying data processing is implemented.