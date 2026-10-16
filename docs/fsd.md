# Functional Specification Document — Core Banking Implementation

> **Read this first.** This is a Markdown conversion of `docs/FSD_Draft_100125_1.pdf`
> (FSD v1.1, dated 10-Jan-2026), made so that later sessions can search it.
>
> **This FSD is a template written for another lender, not for Anchorstone Capital Ltd.**
> It describes a loan-focused core banking system. Do not copy its company-specific
> items into this project. Adapt them for Anchorstone Capital Ltd instead, and ask
> the user when it's unclear how. Template-specific items include:
>
> - **Product names:** Mathree loan, Supa Salo, Quick Cash, Study Abroad Loan,
>   Wasanii Boost, Executive Advance, Check-off, and so on.
> - **The vendor:** "Eazy Books" / "Eazzy Books".
> - **Branches:** the branch list and branch codes (Central Office, Nairobi,
>   Nakuru, …, Kisumu). These also differ between the two lists in this document.
> - **Contact placeholders:** phone numbers like `07xx xxx xxx`, emails like
>   `investments@xxxxx.co.ke`, the sample investor name in the email template,
>   and `(Insert Company Name)`.
> - **Rates, fees, limits and thresholds:** interest bands, fee amounts, the 15%
>   withholding tax, placement minimums and maximums, the 90-day NPL rule, and so
>   on. These are the other lender's business rules, not Anchorstone's. Anchorstone's
>   confirmed rules are in `README.md` and `CLAUDE.md`.
>
> The section closest to what Anchorstone does today is **Funding → Private
> Placements** (investor funds, daily accrual, statements, withholding tax).
>
> **Conversion notes**
>
> - Headings follow the PDF's heading styles.
> - `<!-- page N -->` marks the end of PDF page N, so you can check anything
>   against the original.
> - Tables spanning a page break are joined where the columns matched.
> - Diagram text (the "Logical Loop" on page 8) is kept as plain text only.
> - In some product fee tables, the PDF prints the values on lines offset from
>   their labels. Those tables have been realigned in the order the values
>   appear, and each one carries a note saying so.

## Document history & approval

| Version | Compiled by | Date |
|---|---|---|
| v1.1 | | 10-Jan-2026 |

Approval / sign-off: *"The signatures below indicate that this business requirement document captures all system requirement."* The Reviewed By and Approved By tables (name, department/position, signature, date) are blank in the source.

## List of acronyms

| Acronym | Meaning |
|---|---|
| DD+7 | Due date plus 7 days |
| TAT | Turnaround Time |
| SME | Small & Medium Enterprises |
| GL | General Ledger |
| CRB | Credit Reference Bureau |
| LACE | Loan processing fees |
| PIN | Kenya Revenue Authority Personal Identification Number |
| KYC | Know Your Customer |
| PEP | Politically Exposed Persons |
| AML | Anti Money Laundering |
| FX Transactions | Foreign currency transactions |
| NBV | Net Book Value |
| C2B | Customer to Business |

<!-- pages 1-5: cover, history, acronyms, table of contents -->
## Introduction

The Company is a non-bank financial services company that offers tailor made bridge finance
solutions (loans) to Small & Medium Enterprises (SMEs) and professionals in Kenya.

The Company started its operations in 2014 and currently has 9 branches across the country.

In order to support the intended growth, automation of processes forms a critical part of our
journey which commences with an implementation of a robust core banking software to serve
as the primary application for transaction processing and reporting.

This document describes the requirements of the Company in the core banking system
solution that is to be offered by Eazy Books.

### Key Business Objectives

- Ease of customer management.
- Reduce TAT in processing applications.
- Introduce efficiencies throughout the customer journey and lending process.
- Ease of Financial Reporting.
- Improve document management (storage & retrieval).
- Provide a platform that will provide customers with real-time update on performance
of their facilities as well as system users on their various department duties.

### Key Business Drivers

Our business drivers are:

| Efficiency | As a company, we need all processes automated for us to<br>achieve operational excellence.<br>Efficient processes through automation will help us assign<br>resources rightfully for maximum productivity. |
|---|---|
| Business growth | Systems efficiency will allow us focus more on growing our<br>business through finding new avenues to increase our<br>revenue streams thereby ensuring sustained profitability<br>and growth of the company. |
| Profitability | Improved systems and platforms will allow us to be able to<br>minimize all gaps that bring about unnecessary operational<br>costs while meeting our customers’ needs thereby<br>increasing our net profit turnover. |

<!-- page 6 -->

### Project Scope

|  | Area |  | In- scope |
|---|---|---|---|
| Core Banking System upgrade<br>that allows interoperability with<br>our other 3rd party systems to<br>drive efficiency and value in our<br>processes |  | o Onboarding and Customer Management<br>o Loan Management<br>o Finance & Financial Reporting<br>o Placement/Borrowings Management<br>o Trade Finance/ guarantee Business<br>o Document Management<br>o Risk and Audit Management<br>o Information Technology<br>o Integrations |  |

| Company Name | Number of Branches | Current System | Current Modules |
|---|---|---|---|
| (Insert Company<br>Name) | 0. Central Office<br>1. Nairobi<br>2. Mombasa Rd<br>3. Kitengela<br>4. Thika<br>5. Mombasa<br>6. Eldoret | (Insert Current<br>System) | Finance<br>Credit<br>Placements<br>Risk & Audit<br>ICT |

### Key Assumption

- All data from the old core banking system will to be migrated accurately and
successfully into the new core banking system (Eazzy Books)
- All 3rd party systems will successfully integrate with the new core banking systems via
API.
- All system workflows, settings, special condition will be successfully restored upon
successful implementation of the core.
- All customer instructions will be managed by the core banking system henceforth.

## Customer Journey

Credit is the core function of the Company and all processes are aligned to the mission and
vision of the company.

To create the desired value, all customers are onboarded through a process of KYC validation,
a credit risk analysis is conducted to ascertain affordability of the loan applicant, all documents
are reviewed and verified to the required standard before the collateral is perfected and a
loan limit is awarded by the credit committees.

The customer journey also promotes post disbursement activities that monitor the
performance of the loan to encourage repeat business as well as consumption of other
products under the product profile of the Company.

<!-- page 7 -->
Our Logical Loop

- National ID/Passport •Financial statement
- KRA Pin analytics.
- Certificate of •Bank Statement
Incorporation/Business •M-pesa Statements
certificate
- CRB
- CR12 –Directorship
- Customer visits

Proof of Proof of
Identity Income

Insurance Collateral

- Credit risk
- Trade insurance •Valuation
- Collateral •Joint registration
insurance/business assets. •Car track

## Onboarding - KYC and Facility Documentation

|  | Requirement Subject |  | Requirement Description |
|---|---|---|---|
| Onboarding |  | Customers are onboarded through a facility application.<br>The Core banking system should be able to capture and<br>store the onboarding data after approval.<br>A maker/checker process should be in place for any capture<br>or amendment of static data on the core banking system. |  |

<!-- page 8 -->

| Capturing of Customer Static<br>Data (KYC) | System should allow capturing of customer details as follows<br>NOTE:<br>All field in bold are mandatory fields<br>Client Personal Information (KYC) expected fields.<br>- Classification – (SME (Small, Middle, Large), Retail<br>(Mass, Middle, HNI, Civil Servant)<br>- Salutation<br>- Full Name (As per ID)<br>- Gender<br>- ID Number / Local/ Alien<br>- PIN<br>- Date of Birth<br>- Marital Status<br>- Primary Phone Number<br>- Secondary phone number<br>- E-mail Address<br>- Industry / Sector (Pull down menu to be provided)<br>- Nature of Business<br>- Business Address<br>- Current Home Address<br>- Bank Details<br>- PEP (Politically Exposed Person)<br>- Relationship Manager/Code<br>- Relationship Manager Staff Number<br>- Agent Registration – Name/ Code/ KRA pin/ Phone<br>No / ID No<br>- Branch Code<br>-Employer name<br>-Bank details<br>(Company)<br>- Classification – (SME, Corporate)<br>- Full Company Name (As per Certificate)<br>- Registration Number<br>- PIN<br>- Date of Registration<br>- Primary Phone Number<br>- Secondary phone number<br>- E-mail Address<br>- Industry / Sector<br>- Nature of Business<br>- Business Address<br>- Directors Details (Name, ID number, Phone number<br>date of birth) and Signatories<br>- Bank Details<br>- Risk Factor<br>- PEP (Politically Exposed Person)<br>- Relationship Manager<br>- Branch Code |
|---|---|

<!-- page 9 -->

| Next of Kin Information<br>- Full name<br>- Relationship<br>- Phone Number<br>- Email Address<br>- Home Address<br>Image capture<br>- ID Front<br>- ID Back<br>- Customer Photo<br>- Customer signature<br>- KRA pin<br>- CR12<br>- Certificate of Incorporation<br>- Other Relevant Documents<br>Guarantor Details<br>- Full name<br>- ID Number<br>- PIN<br>- Relationship<br>- Phone Number<br>-Home Address<br>- Email Address |
|---|

## Credit Operations

### Member Account Creation

| Requirement Subject | Requirement Description |
|---|---|
| Member account<br>creation | The main features required for onboarding the various types of<br>customers that the Company maintains are shown below;<br>Ability to capture customer and next of kin information that<br>should include (but not limited to) the following:<br>. Customer Name<br>. Contact Details (telephone, location, etc.) Mandatory<br>. Date of birth<br>. Identification details<br>(See KYC data on the above onboarding module) |
|  | Ability to update the customer static details through a maker<br>checker process as and when required to keep the account<br>information up to date. |
|  | Ability to maintain an audit trail of all changes to the customer<br>static details |

<!-- page 10 -->
The Company maintains a list of blacklisted customers, the
system should have the capability to validate customer (new
and old) against a blacklist

|  | Ability to have a single, comprehensive view of the customer<br>showing all relationships the customer has with the Company,<br>whether as an account holder, signatory, agent, shareholder,<br>guarantor etc. |
|---|---|
|  | Ability to identify existing customer data (ID Number, phone<br>number, KRA pin if captured for a second time through a<br>message pop up so that the same is linked to related<br>parties/accounts. |
|  | Ability to interrogate the customer static details and identify<br>possible duplicates (The system should be able to flag an<br>existing ID, Phone number at the point of onboarding from<br>whichever branch.) |
|  | Ability to merge duplicate customer accounts while maintaining |
|  | Ability to prevent duplicate creation of the same customer<br>through a Company-defined unique identifier such as id<br>number, biometric, company registration number, etc. An ID<br>should not be registered twice in the system. |
|  | Ability to capture customer’s images and signatures at the<br>point of creation of an account. |
|  | Ability to generate reports of all details captured during<br>creation of customer ID & account number. |
|  | Ability to link related parties to customer identifications |
|  | Ability to prompt for additional information where the<br>customer is identified as (POLITICALLY EXPOSED PERSONS)<br>PEP |
|  | Ability to manage different customer types:<br>A – Individual / Local or Foreign<br>B - SME<br>C - Corporate<br>D - Cooperatives<br>E - NGOs<br>F - Investment Groups<br>I - Public Institutions |
|  | · Ability to transfer account from one branch to another |
|  | · Customize account numbers so as to match the accounts<br>across the Company. |
| General Accounts<br>Information | Ability to capture the following account details. These include<br>(but not limited to) the following:<br>. Customer Name<br>. Account Number<br>. Type of Account<br>. Internal Account Name<br>. Customer Identification Number<br>. Authorized Users |

<!-- page 11 -->
The main features required for the signature verification
system are shown below:
- Ability to capture the signatures and image (photos) on the
account number.
- Ability of the system to capture the date when the data on
the system was recorded together with the user’s identity
- Ability to allow for amendment or change of the images held
on file
- Ability of the system to store images and signatures that
have been amended.
Image, Signature &
- When the signature is displayed, ability of the system to
mandate Verification
display an abbreviation of the mandate instructions e.g., any
one to sign, all to sign, one signature from “A list” and one
signature from “B list” etc.
- When a customer has another account then it should be
possible to retrieve data from the other account for the new
account
- Ability to view on-line information about the agent
- Ability to link or group accounts and maintain group
information like director’s information, shareholder information
etc.

### Loan Maintenance & Disbursement

| Requirement Description |
|---|

The system should be able to capture the following information:
- Customer name
- Customer’s address & Contact Information
- National identity number/ Tax Identification Number
- Proprietor/company directors/partners shareholding percentages
- Customer’s operative account number (should automatically link to a loan account)
- County of borrower
- Resident of borrower -Rural, Urban, Peri urban
- Interest – fixed and variable
- Loan repayment dates
- Repayment schedules
- Type of business category
- Sector
- Type of facility
- Security description including valuation date, and revaluation date

Collateral insurance details:
Name of insurance company, Insurance agency, Date of insurance of the asset,
Insurance expiry dates, Type of cover (Third party, Comprehensive, Owner’s goods,
General cartage. Document upload (copy of title deed, copy of logbook, valuation report,
Insurance endorsement, copy of offer letter, change of agency form). The system should
be able to provide these details in a report as well per customer, per loan and a pop-up
dashboard for collaterals insurances that have expired.

<!-- page 12 -->
- Approved facility limit
- Facility Type
- Currency (Ksh/FCY)
- Loan tenor/ period
- Employer Name
- Age
- Gender
- Income brackets.

Guarantor details – Name of guarantor (s), Email address, Phone number, Relationship
to the principal borrower, Physical address, postal address, and amount that the
guarantor has committed to guarantee.

Agent details - Some loans are referred by agents who are not staff, the loans are then
managed by relationship officers. The system to be able to provide a field to capture
below agent details during loan maintenance.
*- Mandatory field

- Agent Full Name *
- ID No*
- KRA pin*
- Phone Number*
- Email address

The agent can either be maintained during member creation then tied to the loan they
refer or during loan maintenance, if an agent has referred more than one loan, it should
be clear to identify and separate each loan tied to them.

Cheque details capture – Ability for the system to capture post -dated cheque details
for every loan application noting the date due to be banked. A report pop-up of the
customer and cheques to be banked should pop daily on the dashboard for credit
operations officers, who should then extract it for reporting per branch.

Details of cheque to be captured
  - Customer name
  - Customer phone number
  - Relationship officer
  - Branch
  - Installment date
  - Installment Amount
  - Loan classification

Agent/ Staff commission payment:
The system should have the ability to maintain parameters to track commission payment
to staff or agent who bring in loans. The commission is paid as a percentage of the loan
amount disbursed. There should also be a report generated daily showing all loans
disbursed with the customer details, branch loan details relationship officer, commission
payment rate, amount and the staff or agent being paid with their payment details

<!-- page 13 -->
(whether bank or M-Pesa no. as well as the Tax percentage deductible and actual tax
amount.

| The system should support below activities.<br>. Restructure<br>. Top ups<br>. Overdrafts<br>. Refinance |
|---|
| Ability for the system to capture static data details for the guarantor |
| Ability to maintain any insurance required as part of the agreement in the system and<br>monitored for renewal. |
| Send SMS alerts to clients for expiring insurance and avail daily report. |
| Ability for workflow to generate disbursement / stage disbursement request when all pre-<br>disbursement conditions are met |
| Ability to generate a printable disbursement receipt showing all charges debited from the<br>amount disbursed |
| Ability to identify and link related parties |
| System should be able to generate offer letters and fees schedule per customer (as per<br>the templates shared) |

### Interest (Interest & Penalty)

|  | Requirement Description |
|---|---|
| Calculate interest for the account in accordance with the interest rate structure in force<br>for the product that defines the account (Flat rate, Reducing Balance) |  |
| Calculate interest accrual entries on 365 days (considering a leap year) |  |
| Prioritization of loan repayment/recovery is Penalty Interest >> Normal Interest >><br>Principal |  |
| Apply the interest on non-performing accounts to interest suspense account (applies to<br>interest and penalty) |  |
| Suspension of interest for non-performing account (normal and penalty). The system<br>should be able to suspend interest for non-performing accounts (any account that goes<br>unpaid for 90 days) and equally adjust the position on repayment. |  |
| Map the breakdown of interest, penalty and any other charge income posted to respective<br>GL per loan account |  |
| Automatically recalculate loan schedules after changes to interest rates and / or tenor. |  |
| Ability to automatically recalculate the loan repayment schedules after changes to interest<br>rates or tenor on the basis of either: |  |
| - Maintaining the current final repayment date for the loan, with consequent modification<br>of the repayment amount. |  |
| - Extending the remaining term of the loan, so the recalculated loan term reflects the<br>period required to amortize the loan at the current, or a specified, repayment amount |  |
| Ability to suspend interest & penalty for NPL accounts, post to respective suspense GL and<br>post to respective income GLs upon payment. |  |
| Automatically reclassify non-performing loan accounts after payments have been made<br>(Normal, Watch, Substandard, Doubtful, Loss.) |  |
| Daily accrual of normal interest and penal interest i.e., debit int. receivable credit int.<br>income for performing loans |  |

<!-- page 14 -->

| Daily accruals of suspended normal interest and penal interest i.e., debit int. receivable<br>credit suspended int. |
|---|
| Automatic calculate interest based on days between installment (Daily interest accrual) |
| Automatically check the breach of the in duplum rule, where breached, flag the accounts<br>and share report. |
| Allow to set a maximum for related parties and do not allow booking of any additional<br>loans. (Maximum loan accounts allowable are 3) |
| Ability to send alerts and notifications to email of concerned parties |
| Automatically send SMS, emails notifications to clients on upcoming installment dates,<br>insurance expiry dates. |
| Allow use of customized interest rates per account under maker checker process. |

### Fees and charges

| Requirement Description |
|---|
| Ability to charge fees and charges as per the product specification that include;<br>o Lace (Loan Processing Fees)<br>o Insurance Risk Fund<br>o Bank charges/ RTGS<br>o CRB Fees<br>o Legal stamp fees<br>o Membership fees<br>o Tracking fees – Should be charged monthly<br>o Valuation fees<br>o Insurance premium charges<br>o Company search fees |
| Ability to deduct fees monthly as required (tracking fees and insurance premium) |
| Ability to Cleary show the fees debited from the loan account. |
| Ability for the fees to affect the principal balance and be cleared as principal amount |
| The system should be able to capture other charges related to an existing facility such as<br>additional storage fees for a repossessed collateral, the fees captured should be visible on<br>the customers loan statement and should be part outstanding balance that a customer<br>should pay. |

### Loan Repayments

| Ability to maintain various repayments frequency as, Daily, Weekly, Fortnightly,<br>Monthly, Quarterly, Termly, Half-yearly, Yearly, bullet etc.<br>The system should provide a report showing expected repayments per month for all<br>products. |
|---|
| Allow for repayment schedules with diverse frequencies (principal & interest, interest<br>only, bullet interest and principal) |
| The system should allow for early settlements on loan accounts and surcharge as per<br>the respective product |
| The system should maintain a standard repayment amount based on the term of the<br>loan, current interest rate and loan balance as per the loan schedule |
| Allow the system to accept Lump sum repayments to the principal. |

<!-- page 15 -->
| The system to allow posting of payments in selected loan accounts where the customer<br>has more than one loan account. |
| Allow change of repayment dates through a maker checker process |
| Allow for loan re-scheduling i.e. dates and amounts |
| The system provides early settlement statement including the loan balance, including<br>all necessary fees as per the respective loan product |
| Automatic deduction of due loan installment from the member collection account |
| Ability to provide a controlled process for closure of a loan account, including:<br>. Automatic charge of agreed interest at the point of account closure especially<br>instances of early settlement.<br>. Automatic generation of closing account entries<br>. Termination of periodic payments such as tracking fees / insurance premium upon<br>loan account closure<br>. Notification to credit reporting agency CRB<br>. Issue of clearance letter to customer(s)<br>. Release of securities<br>. Cancellation of insurances |
| Ability of the system to allow reversal and closure loan accounts with interest /penalty<br>in suspense and receivable |
| When repayment is received it should be posted in the system which should<br>automatically generate the appropriate entries to adjust the loan balance in this order;<br>Penalty>>Interest>>Principal.<br>In case of collateral disposal, the repayment should follow this order;<br>Principal>>Interest>>Penalty. |
| Ability to avail loan settlement statements with ability to charge future interest<br>automatically |
| Ability to stop interest or suspend interest even for performing accounts with approval |
| Clearly display the closing balance of a loan, the interest posted to income, suspended<br>interest, normal accrued interest, accrued penal interest other charges such as<br>tracking, repossession, storage fees |

### Check off

| Ability to book the loan as per the product specification and disburse gross amount to<br>the customer |
|---|
| The system should have the ability to capture check off customer employers from a<br>drop-down list which should be pre maintained. |
| No penalty interest charge on this product |
| Ability for user to view monthly repayments break down in terms of interest, principal,<br>credit life, admin fees, insurance |
| Ability to allocate instalment to the respective ledgers based on the remitted byproduct |
| Ability to post bulk payments and auto reconcile |

### Security/ Collateral Management

Avail a register of all securities provided by each loan account and attach multiple
securities to a specific loan account

<!-- page 16 -->

| Ability to identify if the security is for the guarantor or principal borrower and include<br>contact name and collateral details |
|---|
| Ability for the system to identify and report where loan values are greater than<br>securities registered |
| Ability to see loan to value per loan account |
| Ability to avail expired insurance and valuation report for renewal and revaluation such<br>that the facility will indicate as unsecured at that point |
| Ability for the system to handle a security offered in support of many loans and a loan<br>supported by more than one security (shared collateral for multiple loans) |
| Ability for a customer to replace one security with another, subject to appropriate fees<br>and government charges and necessary approvals |
| Ability to release individual security subject to the outstanding loan balance |
| Ability for the system to provide Loans for valuation and revaluation of securities<br>including shares based on valuation expiry dates. |
| Does the system cater for diary lists e.g., for reminders for need for revaluation of<br>securities and renewal of insurance? |
| Can the system produce instruction advice for the preparation or renewal of security<br>documentation, and record the current status of these preparations in progress |
| Avail the range of details relating to securities (including but not limited to) the<br>following:<br>(a) Motor Vehicle<br>(b) Land Titles<br>(c) Debentures<br>(d) Letters of Set- Off<br>(e) Guarantees & Indemnities<br>(f) Treasury Bills and Bonds;<br>(g) Shares<br>(h)Others |
| The system should be able to capture the following collateral details:<br>• Name for the collateral owner/ holder<br>• Location of Collateral<br>• Collateral Value (OMV, FSV and Insurance Value)<br>• Identification number or Certificate number of the collateral<br>• Detailed description of the Collateral<br>• The Last valuation date of the collateral |

### Restructuring/ Rescheduling

| Ability to reschedule loan facilities |
|---|
| Ability to restrict the restructuring of a particular account to maximum of 3 times. |
| Ability to generate an alert and or error message if a particular account is to be<br>restructured beyond 3 times. |
| Ability to distinguish between a restructure and any other amendments done on an<br>account e.g., change in interest rates, reduction/increase in loan tenor, etc. |
| Ability to automatically recover restructuring fees once the restructure is done. |

<!-- page 17 -->

### Provisioning

| The bad loans should be classified as per the Company's policy guidelines below:<br>· Normal<br>· Watch<br>· Sub standard<br>· Doubtful<br>· Loss |
|---|
| Ability to suspend accrued interest to the Company's interest in suspense account(s)<br>for accounts classified as non-performing. |
| Create specific provisions report for loan accounts. |

### Recoveries and collection

| Ability to maintain an accurate position of scheduled repayments versus actual<br>repayments such that deviations from the schedule can be detected and actioned<br>promptly. |
|---|
| Ability to provide a diary for recording of collections activity. (Notes per account) |
| Ability of the diary to allow recording of free form text, system events (such as issue of<br>correspondence) and external events (such as telephone contact) |
| Ability to generate customer correspondence, including reminder letters, notice of<br>default etc., automatically generated by the system in accordance with defined<br>parameters |
| Where the Company enters into special collection arrangements with the customer for<br>reduction of outstanding debt, these arrangements monitored by the system and non-<br>compliance reported to debt recovery. (Pop ups) |
| Ability to charge fees for overdue accounts in accordance with the product definition<br>i.e., tracking fees, repossession, storage, advertisement, tracker tampering. |
| Ability for the system to update /report on accounts with matured credit life. |
| Ability to charge penalty interest on any outstanding amounts in accordance with the<br>product definition 7 days past due date. (Applies to all products) |
| Ability to avail facilities for notification to the Credit Reference Bureau of overdue<br>payments and serious credit infringements according to defined parameters |
| Ability for the system to maintain a history of arrears for each account |
| Ability to manually stop any interest accrual on non-performing loans classified that are<br>beyond 90days in default per account. |
| Debt Recovery<br>The system should have the ability to generate below notices as per the templates<br>shared.<br>Demand Notice<br>Proclamation & repossession notices<br>Sales notices – Email & SMS<br>Disposal of assets, provision for upload of disposal of assets forms and documents.<br>Debt recovery reports<br>o System should provide a report showing all accounts under the debt recovery<br>classification (90 days and above) with all customer, loan and relationship<br>officer fields.<br>o Report showing the loan account in default and the collateral type<br>o Report showing loan account balances and the collateral value |

<!-- page 18 -->

### Accounts Under Litigation

| Ability to flag & show accounts that are under litigation. |
|---|
| Ability to manually stop any interest accrual on accounts under litigation on approval |

### Insurance

| Ability to capture the following information<br>- Insurance Company<br>- Sum Insured<br>- Premium Paid<br>- Receipt Number<br>- Type of insurance<br>- Policy number<br>- Policy start date<br>- Policy expiry date |
|---|
| Ability to amend policy start and expiry date on renewal for active loan accounts. |
| Ability to automatically recover the premium due from the customer's operative<br>account |
| Ability to generate alerts for insurance premium due to expire within a given "N" period |
| Ability to track claims against insurance companies especially credit life and Collateral<br>written off |

### Written Off Portfolio

| Ability to pass the necessary entries for write off. In view of all appropriate GLs<br>(Suspense and receivable) |
|---|
| Ability of the system to nil off any remaining provisions and interest in suspense after<br>write-off |
| Ability to automatically flag/ show a written off status for a closed loan account |
| Ability to maintain a diary of the amount written off |
| Ability for the system to place a lien equivalent to the written off balance on the<br>member operative account(s) |
| Ability to automatically recover funds from a member account whose loans have been<br>written off |
| System should not overdraw member accounts or overpay loan accounts – whether<br>manually or automatically. |

### Reporting

| Automatically generate real time reports at set times and save them |
|---|
| Provide budget information for credit facilities with Month to date, year to date,<br>variances, amounts, repayments, par etc. |

<!-- page 19 -->
| Avail statical reports covering Loan applications, interest rates fees and charges<br>(including Discounted fees) |
| Loan disbursement report including outstanding balances reporting by location,<br>industry, loan type, age, income breakdowns/contact |
| Classify loan portfolio by industry/amounts/securities/currency/tenor/interest<br>rate/Monthly instalment/Interest/ principal /penalty balances/collateral<br>number/employer name /collateral market value and forced sale value/retirement<br>date or other defined parameters/instalment due |
| Report on balances/repayments overdue and/or in excess of the amount sanctioned,<br>together with the amount and number of repayments overdue |
| Report on outstanding loan balance including, principal balance accrued<br>interest/penalty receivable, interest /penalty posted to income, suspended /penalty<br>interest on all facilities as at a specified date. |
| Report of accounts where the interest has been stopped showing the:<br>· customer’s name<br>· Account number<br>· Date interest was stopped<br>· Reason for interest stoppage<br>· Type of facility<br>· Amount |
| Provide a list of credit facilities balances or installments due for payment within a user<br>specified period |
| Provide the printing of letter quality: (Overdrafts)<br>· Notice of drawdown<br>· Initial drawdown<br>· Interest payment due<br>· Insurance premium due<br>· Repayment due<br>· Notice of renewal<br>· Maturity |
| Report the credit exposure by:<br>· Branch<br>· Region<br>· County<br>· Town (classify as urban, peri urban, rural)<br>· Consolidated<br>· Country<br>· Industry<br>· Interest rates<br>· Collateral type<br>· Gender /Registered Business<br>· Type of business status e.g., partnership etc.,<br>· Loan type<br>· Employer<br>· Sectors<br>· Income |
| Report on rescheduled facilities and rescheduled dates together with the resulting<br>rescheduled payments |

<!-- page 20 -->
| Report on non-performing accounts with:<br>· Name of borrower<br>· Contact<br>· Employer name<br>· Principal outstanding<br>· Interest outstanding<br>· Penalty interest outstanding<br>· Instalment amount<br>· Type of facility<br>· Days in arrears<br>· Loan ageing category -Normal, watch, substandard, doubtful, loss<br>· Collateral attached to loan<br>· FSV of collateral attached to loan<br>· Date amount due |
| Report on any changes to the interest rate on accounts on a daily basis |
| Report on transactions input on a daily basis to all recovery accounts |
| Inquire on the history of a customer facilities over the last 7 years |
| Report on loans and advances secured by each security type |
| Print separate lists for outstanding balances for each type of facility together with the<br>interest/penalty posted to income and suspended. |
| Ability to generate a report showing the total exposure of the client showing both the<br>On and Off-Balance sheet items e.g., loans, guarantees, LCs, overdraft |
| The arrears report should breakdown the arrears between the principal, interest,<br>penalty, and other charges that make up the current arrears position |
| Ability to spool department/product/branch performance reports showing the income<br>(interest, non-interest) that has been off a customer/ account? |
| Generate a report of the off-balance sheet items like guarantees, letters of credit etc. |
| Provide a report showing the income earned from each loan account in a given<br>period |
| Ability to send out alerts for exceptional behavior on some accounts e.g., loan<br>instalments that haven’t fallen due, interest that hasn’t been applied, payments<br>liening in member account past due date. |
| Segmentation of the loan book on various set parameters like employer, business<br>units, regions, age, income, region, sector |
| Report on daily repayments. (Separate third-party payments & Client’s payments) |
| Insurance expiry report |
| Report for all exceptions per product generated monthly |
| Revenue assurance report |

### Special Conditions

| Ability to suspend interest for performing accounts but still charge on client’s account. |
|---|
| Manual intervention to repay principal, interest and penalty for specific accounts that<br>are non-performing. |
| Ability to flag a loan account that has commission paid and to include agent details |
| Ability to stop interest & penalty charge on a loan account |
| Avail option for automatic interest and penalty waivers |
| Avail option for charging interest on early loan settlement automatic charging as per<br>specified number of months and pay off of the same. |

<!-- page 21 -->
| All transaction posting must be tagged to a specific loan number or member number. |
| Ability to flag access by staff to accounts not tagged to them, either per product,<br>department, high level accounts or access to reports/GLs. |
| Maker and checker ability that is departmental. |
| Ability to see maintainer(makers) and approver (Checkers) on reports. |
| 360 View of a client in one window |
| Client anniversary dates and client birth dates, should provide filters to mark for who<br>should receive notifications. |
| No overdrawing of loan or member collection account. |
| Is the system able to capture maturity dates for a customer with overdraft facilities |
| For preferential charges, can the system allow for capturing the same at customer<br>and not at account or product level under maker/checker. |
| Ability to provide alerts and reminders to relationship managers of loan obligations<br>that are to fall due in the near future - timeframe to be defined by the Company |
| Ability to capture date reviews/changes and automatically charge a review fee on the<br>defined due date |
| Ability to capture preferential charges at customer and not at account or product level |
| The system should not allow for automatic overdrawing of member accounts and<br>neither should it allow for an overpayment of loans. |
| Ability to charge other fees monthly |

## Loan Products and Behavior

### Loan Products

1. Business Loans
a) Monthly installments (Principal & Interest) -Tenor 24 months
b) Bullet interest & Bullet principal – Tenor 3 months
c) Monthly interest paying & bullet principal -Tenor 3 months
d) Reducing balance (partners)
2. Check-Off Loans
3. Supa Salo
4. Quick Cash
5. Executive Advance
6. Import Duty Finance
7. Mathree Loan
8. Staff Loan
9. Study Abroad Loan
10. Wasanii Boost

### Loan Accounting Rules

The accounting rules have stipulated the transactions that will be processed by the core
banking solution based on the interest accounting basis applied for the Company's loan
products.

<!-- page 22 -->

#### Business Loan

#### a) Business Loan – Tenor 24months

Repayment on monthly basis both principal and interest component as per the loan schedule.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly |  | 3.5-5% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company searches fees | 1,500 |  |

**Loan Disbursement**

- Dr: Business loan account GL (Amount financed to customer)
- Cr: Member Collection account

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB Fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Risk fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

<!-- page 23 -->
- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

**Interest Charge (Performing account)**

- Dr: Interest Receivable GL (Specific Product)
- Cr: Interest Income GL (Specific Product)

**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Interest Charged on a Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Interest Payment on a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date) Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL

**Penalty payment - a Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

**Penalty Charge (charged 7th day past due date) non-Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

**Penalty payment - a non – Performing account**

- Dr: Member Collection account

<!-- page 24 -->
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### b) Business Loan –Bullet interest & bullet principal -Tenor 3 months

Repayment on this facility type is made at the end of the agreed period for both interest and
principal.

Account accrues daily and upon maturity if the account is funded it posts the interest payable
to income GL, if the account is not funded its posts the interest payable to suspense GL

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly |  | 3.5-5% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company searches fees | 1,500 |  |

**Loan Disbursement**

- Dr: Business loan account GL (Amount financed to customer)
- Cr: Member Collection account

- Dr: Member Collection account
- Cr: Bank Account

**Loan Charges**

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB Fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

<!-- page 25 -->
- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Risk fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

**Interest Charge (Performing account)-Upon Maturity**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Non – Performing account (91st day)-if account is not funded upon maturity**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Payment of a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

Penalty Charge (charged 7th day past due date)-if account is not funded upon
**maturity**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

Penalty payment a non – Performing account

<!-- page 26 -->
- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### c) Business Loan –Monthly interest paying & bullet principal -Tenor 3 months

Repayment on this facility type is such that the client pays interest monthly with principal due
on maturity of the tenor.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly |  | 3.5-5% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company searches fees | 1500 |  |

*Realigned: in the PDF these values sit on lines offset from their labels. They are placed here in the order printed, which matches the other business-loan tables.*

**Loan Disbursement**

- Dr: Business loan account GL (Amount financed to customer)
- Cr: Member Collection account

**Loan Charges**

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)

<!-- page 27 -->
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Risk fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

**Interest Charge (Performing account) - Monthly**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Payment of a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge on Interest (charged 7th day past due date) Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL

Penalty payment a Performing account

<!-- page 28 -->
- Dr: Member Collection account
- Cr: Penalty Receivable GL

Penalty Charge on Interest (charged 7th day past due date) non-Performing
**account**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

**Penalty payment a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### d) Business Loan –reducing balance (partners)

Repayment on this facility type is made monthly for both interest and principal on reducing
balance interest calculation method.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly |  | 3.5-5% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company searches fees | 1500 |  |

*Realigned: in the PDF these values sit on lines offset from their labels. They are placed here in the order printed, which matches the other business-loan tables.*

Loan Disbursement

<!-- page 29 -->
- Dr: Business loan account GL (Amount financed to customer)
- Cr: Member Collection account

**Loan Charges**

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Risk fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

**Interest Charge (Performing account)**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Interest Charged on a Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

Interest Payment on a non- performing loan

<!-- page 30 -->
- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date) Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL

**Penalty Charge (charged 7th day past due date) non-Performing account-91st Day**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

**Penalty payment on a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### Check off

Monthly instalment is computed as below.

Total installment per month = Installment(P+I) + Insurance + Admin fee + Processing fee

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Principal |  |  |
| Interest rate Monthly (flat rate) |  | 2.5% |
| Loan processing fees |  | 3% |
| Risk Fund |  | 2.5% |
| Ledger Fees |  | 150 |

**Loan Disbursement**

- Dr: Check off loan account GL (Amount financed to customer)
- Cr: Member Collection account

- Dr: Member collection account

<!-- page 31 -->
- Cr: Bank

**Loan Charges (performing account) as per repayment schedule**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

- Dr: Loan processing fee receivable GL
- Cr: Loan processing fee Income GL

- Dr: Risk Fund Receivable GL
- Cr: Risk fund GL Liability GL

- Dr: Ledger Fees Receivable GL
- Cr: Ledger fees Income GL

**Loan payment (Performing account)**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Member Collection account
- Cr: Loan processing fee receivable GL

- Dr: Member Collection account
- Cr: Risk Fund Receivable GL

- Dr: Member Collection account
- Cr: Ledger Fees Receivable GL

**Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

- Dr: Loan processing fee receivable GL
- Cr: Loan processing fee Suspense GL

- Dr: Risk Fund Receivable GL
- Cr: Risk fund GL Suspense GL

- Dr: Ledger Fees Receivable GL
- Cr: Ledger fees Suspense GL

Payment of a non- performing loan

<!-- page 32 -->
- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

- Dr: Member Collection account
- Cr: Loan processing fee receivable GL

- Dr: Loan processing fee Suspense GL
- Cr: Loan processing Income GL

- Dr: Member Collection account
- Cr: Risk Fund Receivable GL

- Dr: Risk Fund Suspense GL
- Cr: Risk fund Liability GL

- Dr: Member Collection account
- Cr: Ledger Fees Receivable GL

- Dr: Ledger Fees Suspense GL
- Cr: Ledger Fees Income GL

#### Supa Salo

Repayment on monthly basis both principal and interest component as per the loan
schedule.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly (flat rate) |  | 5% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company search fees | 1,500 |  |

*Realigned: in the PDF these values sit on lines offset from their labels. They are placed here in the order printed, which matches the other business-loan tables.*

**Loan Disbursement**

- Dr: Supa salo loan account GL (Amount financed to customer)
- Cr: Member Collection account

<!-- page 33 -->
**Loan Charges**

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB Fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Risk fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

**Interest Charge (Performing account)**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid on a performing account**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Interest Charged on a Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Payment of Interest on a non- performing loan**

- Dr: Member Collection account

<!-- page 34 -->
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date) - Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL

**Penalty payment on a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### Overdraft Facility

Repayment is based on monthly utilization/ drawdown with interest on drawdown amount
payable on monthly basis.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly (flat rate) |  | 5-7% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company searches fees | 1,500 |  |

Loan Charges Amount

<!-- page 35 -->
- Dr: Loan Overdraft Account (Total Loan Charges Amount)-from the Set OD Limit
- Cr: Member Collection

**Loan Charges**

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB Fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Risk fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

**Loan Disbursement**

- Dr: Loan Overdraft account (Drawdown Amount)
- Cr: Member collection account

- Dr: Member collection account (Drawdown Amount)
- Cr: Bank

**Interest Charge (Performing account)**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid on a Performing Account**

- Dr: Member Collection account
- Cr: Interest Receivable GL

<!-- page 36 -->
**Interest Charged on Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Interest Payment of a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date) Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL

**Penalty paid on a performing Account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

**Penalty Charge (charged 7th day past due date) non-Performing account-91st Day**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

**Penalty payment a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### Executive Advance

Repayment on monthly basis both principal and interest component as per the loan
schedule.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly (flat rate) |  | 5% |

<!-- page 37 -->
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company search fees | 1,500 |  |

**Loan Disbursement**

- Dr: Executive loan account GL (Amount financed to customer)
- Cr: Member Collection account

**Loan Charges**

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB Fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Risk fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

<!-- page 38 -->
**Interest Charge (Performing account)**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Interest on Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Payment of interest on a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date) Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL
**Penalty paid on a performing Account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

**Penalty Charge (charged 7th day past due date) non-Performing account-91st Day**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

**Penalty payment a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

<!-- page 39 -->

#### Import Duty Finance

One month loan facility.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly (flat rate) |  | 5% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company search fees | 1,500 |  |

**Loan Disbursement**

- Dr: Import duty finance loan account GL (Amount financed to customer)
- Cr: Member Collection account

**Loan Charges**

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB Fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Risk fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

<!-- page 40 -->
- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

**Interest Charge (Performing account)**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Interest Charge on Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Payment of Interest on a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date) Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL

**Penalty paid on a performing Account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

**Penalty Charge (charged 7th day past due date) non-Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

**Penalty payment a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

<!-- page 41 -->
- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### Mathree loan

Repayment on monthly basis both principal and interest component as per the loan
schedule.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly (flat rate) |  | 5% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company search fees | 1,500 |  |

**Loan Disbursement**

- Dr: Mathree loan account GL (Amount financed to customer)
- Cr: Member Collection account

**Loan Charges**

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB Fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

<!-- page 42 -->
- Dr: Member collection account (Risk fund)
- Cr: Risk fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

**Interest Charge (Performing account)**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Interest Charge on Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Interest Payment of a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date) Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL

**Penalty paid on a Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

<!-- page 43 -->
**Penalty Charge (charged 7th day past due date) non-Performing account – 91st Day**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

**Penalty payment a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### Staff loan

Repayment on monthly basis both principal and interest component as per the loan
schedule.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly (reducing balance) |  | 1.5% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | n/a |  |
| Risk Fund | 1% |  |

**Loan Disbursement**

- Dr: Staff loan account GL (Amount financed to customer)
- Cr: Member Collection account

Loan Charges

<!-- page 44 -->
- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB Fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Risk fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

**Interest Charge (Performing account)**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Interest Charge on Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Interest Payment on a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL

<!-- page 45 -->
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date) Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL

**Penalty paid on a Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

**Penalty Charge (charged 7th day past due date) non-Performing account (91st Day)**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

**Penalty payment on a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### Asset Finance

Repayment on monthly basis both principal and interest component as per the loan schedule.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly (flat rate) |  | 4.5% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company search fees | 1,500 |  |

*Realigned: in the PDF these values sit on lines offset from their labels. They are placed here in the order printed, which matches the other business-loan tables.*

<!-- page 46 -->

**Loan Disbursement**

- Dr: Asset Finance loan account GL (Amount financed to customer)
- Cr: Member Collection account

**Loan Charges**

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB Fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Insurance sinking fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

**Interest Charge (Performing account)**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

<!-- page 47 -->
**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Interest Charge on Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Interest Payment on a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date) Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL

**Penalty paid on a Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

**Penalty Charge (charged 7th day past due date) non-Performing account (91st Day)**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

**Penalty payment a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### Payday Advance

Repayment on monthly basis both principal and interest component as per the loan schedule.

<!-- page 48 -->

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly (flat rate) |  | 4.5% |
| Penalty Rate (monthly) DD+7 |  | 3% |
| Membership fees | 1,000 |  |
| Loan application fees | 3% |  |
| Risk Fund | 2.5% |  |
| Tracking fees |  | 2,000 |
| Legal Fees | 500 |  |
| Bank transfer fees | 1,000 |  |
| CRB Fees | 300 |  |
| Company search fees | 1500 |  |

**Loan Disbursement**

- Dr: Payday Advance loan account GL (Amount financed to customer)
- Cr: Member Collection account

- Dr: Member Collection account
- Cr: Bank Account

**Loan Charges**

- Dr: Member collection account (Membership fee)
- Cr: Membership fees GL (Income GL)

- Dr: Member Collection account (Loan processing fee)
- Cr: Loan processing fee (Income GL)

- Dr: Member collection account (CRB fees)
- Cr: CRB Commissions GL (Income GL)

- Dr: Member collection account (Legal Fees)
- Cr: Legal stamp fee GL (Income GL)

- Dr: Member collection account (Tracking fees)
- Cr: Tracking fees GL (Settlement GL)

- Dr: Member collection account (Risk fund)
- Cr: Insurance sinking fund GL (settlement GL)

- Dr: Member collection account (Insurance premium)
- Cr: MCA subsidiary payable (Settlement GL)

<!-- page 49 -->
- Dr: Member collection account (Company search fees)
- Cr: Search fees GL (Settlement GL)

- Dr: Member collection account (Net amount payable to client)
- Cr: Bank

**Interest Charge (Performing account)**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

**Non – Performing account (91st day)**

- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Payment of a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date) Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Income GL

**Penalty paid on a Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

**Penalty Charge (charged 7th day past due date) non-Performing account**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

<!-- page 50 -->
**Penalty payment a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

#### Insurance Premium Financing

Repayment on monthly basis both principal and interest component as per the loan schedule.
First loan instalment is payable before loan disbursement.

| Product Fees | One-off payment | Monthly charge |
|---|---|---|
| Interest rate Monthly (flat rate) |  | 2% |
| Penalty Rate (monthly) DD+7 |  | 3% |

**Loan Disbursement**

- Dr: Insurance premium Financing loan account GL (Amount financed to customer)
- Cr: Member Collection account

- Dr: Member Collection account
- Cr: Assurance premium GL

Any account falling due, and the member account is non funded should be classified as non-
performing account.

**Interest Charge (Performing account) If the account is funded**

- Dr: Interest Receivable GL
- Cr: Interest Income GL

**Interest paid**

- Dr: Member Collection account
- Cr: Interest Receivable GL

Interest Charge (Performing account) If the account is non- funded

<!-- page 51 -->
- Dr: Interest Receivable GL
- Cr: Interest Suspense GL

**Payment of a non- performing loan**

- Dr: Member Collection account
- Cr: Interest Receivable GL

- Dr: Interest Suspense GL
- Cr: Interest Income GL

**Penalty Charge (charged 7th day past due date)**

- Dr: Penalty Receivable GL
- Cr: Penalty Suspense GL

**Penalty payment a non – Performing account**

- Dr: Member Collection account
- Cr: Penalty Receivable GL

- Dr: Penalty Suspense GL
- Cr: Penalty Income GL

## Trade Finance

### Definitions

Trade Finance – is the provision of any form of financing that enables a trading activity to
take place, this includes Local purchase orders, Local Service Orders, provision of bank
guarantees, bid securities, performance securities and advanced payment guarantees to
enable contractors and suppliers meet contractual terms.

Cash Margin – non-interest earning deposit held as security for a loan/guarantee issued to
a customer.

### Products

1. Bid Bond/ tender securities – is a guarantee by a bank provided to a tendering
institution by bidder, stating that the bidder, has capability to undertake the
tendered project if selected by the institution.
2. Performance Bond – written guarantee by a bank/insurance company issued to a
procuring entity on behalf of the winning bidder/contractor to guarantee successful
completion of the awarded project/contract.
3. Advanced Payment Guarantee- is a guarantee issued by a bank on behalf of its
clients to a procuring entity, to secure upfront payments for jobs awarded but not
executed.

<!-- page 52 -->
4. Bank Guarantee – is an assurance from a lending institution ensuring that liabilities
of a debtor will be met.
5. Letter of Credit – written undertaking by a bank given to a seller (beneficiary) at
the request and in accordance with a buyers (applicant) instruction to effect payment
of a stated amount, against stipulated documents and within a prescribed time limit.

| Product | Definition | Features |
|---|---|---|
| Bid Bonds | A Tender security/Bid bond<br>is a guarantee by a bank<br>provided to a tendering<br>institution by a bidder,<br>stating that the bidder, has<br>the capability to undertake<br>the tendered project if<br>selected by the institution. | Processing within 1 hour<br>Maximum amount:20,000,000<br>unsecured. Amounts above that require<br>10% cash cover.<br>Tenor: Maximum 12 months<br>Charge of 1.5%-2% per quarter with a<br>minimum of Kshs. 3,500.<br>Key Documentation<br>Copy of the contract document calling<br>for the bond/tender document<br>Fill guarantee request form. |
| Performance Bond | Performance bonds are<br>designed to ensure that<br>goods are delivered, or<br>services rendered in<br>accordance with the terms<br>of a contract. | Cash cover:10-20% of guarantee<br>amount depending on the bank used.<br>Conventional Security: Logbooks to<br>cover 70%.<br>Commission: 2% per quarter or a<br>minimum of 1.5% per quarter.<br>Customer deposits equivalent of<br>Counter insurance to cater for the<br>balance of the performance bond<br>beyond the cash cover.<br>Key Documentation<br>Fill guarantee request form<br>Audited financials for the last 2 years<br>Copy of Contract award letter<br>Performance bond wording template<br>Copies of company registration<br>certificate and latest CR12<br>Detailed company profile<br>Last twelve months certified bank<br>statements<br>Copies of directors' ID’s and KRA PINs<br>Copies of complete and ongoing<br>contracts<br>Copy of the proposed collateral/security<br>i.e. vehicle logbook. |

<!-- page 53 -->
| Advanced Payment<br>Guarantee | Advance Payment<br>Guarantee is issued by a<br>bank on behalf of its client<br>to a procuring entity, to<br>secure upfront payments<br>for jobs awarded but not<br>executed. | Access of up to 50% of the APG<br>Conventional Security-Logbooks/Title<br>deed to cover 50%<br>Commission of 3% per quarter or a<br>minimum of 2.5% per quarter<br>Key Documentation<br>Fill guarantee request form<br>3 Latest audited financials including<br>latest management accounts<br>Copy of Contract award letter<br>APG wording template<br>Copies of company registration<br>certificate and latest CR12<br>Detailed company profile<br>Most recent twelve months bank<br>statements<br>Copies of directors' ID’s and KRA PINs<br>Copies of completed and ongoing<br>contracts<br>Copy of the proposed collateral/security<br>i.e. Title deed or vehicle logbook. |
| Bank Guarantee | A bank guarantee is an<br>assurance from a bank<br>ensuring that liabilities of a<br>debtor will be met. | 100% cash cover<br>Commission of 2% per quarter<br>Key Documentation<br>Fill guarantee request form<br>3 Latest audited financials including<br>latest management accounts<br>Copy of Contract award letter<br>Bank guarantee template<br>Copies of company registration<br>certificate and latest CR12<br>Detailed company profile<br>Most recent twelve months bank<br>statements<br>Copies of directors' ID’s and KRA PINs<br>Copies of complete and ongoing<br>contracts<br>Copy of the proposed collateral/security<br>i.e. Title deed or vehicle logbook. |

### General Requirements

1. Ability for the system to validate sufficiency of balance / limit before committing any
transaction.
2. Ability to integrate with the company Anti Money Laundering System and
validate beneficiary AML status before processing.
3. Ability to manually authorize and approve / reject transactions identified by the

<!-- page 54 -->
AML system or committee approved/ rejected applications.
4. Ability to review transaction details and approve it in the system. On approval
do the following but not restricted to:
i. System to pass necessary accounting entries
ii. Voucher to be generated
iii. If the Customer is under E-Banking, electronic copy of the voucher is
mailed to the Customer
5. Ability to review transaction details and do the following:
i. return transaction details back to the data entry personnel for
modifications, if required
ii. cancel it in the system, if required
6. Ability to pass necessary accounting entries at each stage of the transaction

| Trade Finance Accounting Process |  |  |
|---|---|---|
| To recognize money the customer has<br>deposited either through cash, M-Pesa<br>cheque in the respective bank for the<br>guarantee applied for. | DR | Respective bank |
|  | CR | Member account |
| To recognize deduction of all charges that<br>the bank has charged the Company as<br>regards the guaranteed product. | DR | Member account |
|  | CR | Respective bank |
| To recognize deduction of cash margin by<br>the bank. | DR | Cash margin of respective bank |
|  | CR | Respective bank |
| To recognize deduction of CRB (Credit<br>reference bureau) charge by the<br>Company. | DR | Member account |
|  | CR | CRB income |
| To recognize deduction of CR 12 search<br>charge by the Company. | DR | Member account |
|  | CR | CR 12 report |
| To recognize income that has been earned<br>from the guaranteed product. | DR | Member account |
|  | CR | Guarantee income |
|  | DR | Respective bank |

<!-- page 55 -->
| When the guarantee expires the bank<br>refunds the Company with the cash<br>margin. | CR | cash margin of respective bank |
| When the guarantee expires the client will<br>request for a refund of the cash margin<br>VIA CHEQUE, MPESA OR CASH. In this<br>step, the client account should go to zero.<br>(if client had different products maturing<br>different days then the account won’t go<br>to zero.) | DR | member account |
|  | CR | Respective bank |

## Finance

### Finance Module requirements

|  | Requirement Subject |  | Requirement Description |
|---|---|---|---|
| Accounting and finance functions |  | The system should have the ability to handle the below<br>accounting and finance functions;<br>a) Chart of accounts: customizable; can one create<br>multiple COAs, for generation of different reports<br>with the following structure: Assets, Liabilities,<br>Capital (net assets), Revenues, Expenses<br>b) Category (current/long term or other account<br>groups), by number ranges<br>c) Branch code<br>d) Transaction codes by type of transaction (user<br>access to posting functions)<br>e) Subsidiary ledgers (Facilities, Deposit, Account<br>Payable, Account Receivable)<br>f) Are these functions fully integrated? Integrated<br>on-line and real time accounting modules<br>g) Are they online and real-time functioning<br>accounting modules? |  |

<!-- page 56 -->

|  | h) Support user defined accounting periods<br>i) Ability to support drill down/ navigation feature<br>on tracing transactions<br>j) Ability to handle accrual accounting<br>k) Ability to provide a balance sheet and P& L per<br>business segment |
|---|---|
| Account Codes | The system should have a functionality.<br>a) Provide flexibility to generate accounts based on<br>predefined rules.<br>b) To be able to retrieve the TB for previous years<br>and not transactions only<br>c) To facilitate segregation of revenue and expense<br>accounts by division, department and work, cost,<br>product, or profit center. |
| Batch Posting | The system should have the capability to:<br>a) Create and post journal entries online or in batch<br>b) Create multiple batches of journal entries at one<br>time<br>c) Allow validation to ensure only balanced batch<br>entries are updated to the system (debits equal<br>credits)<br>d) Provide or allow “rolling-back” unfinished<br>transaction posting feature.<br>e) Does the system allow suspension of unbalanced<br>batch for later posting?<br>f) Maker-checker function at the posting of<br>transactions and journal entries.<br>g) Auto-serialization of journal entries and<br>transactions posting. |
| Cash Receipts Journal/Bank<br>Account Reconciliation | The new system must contain an integrated component<br>that provides a cash receipts journal from which the<br>posting of cash receipts/bank deposits from all sources<br>(MPESA, AIRTEL Money, Automated Clearing House<br>(ACH), credit cards, wire transfers, etc.) to the GL<br>occurs.<br>The banking feature is expected to automate the<br>reconciliation of bank statement(s) to the respective GL<br>account(s) including the ability to electronically import<br>bank account data (deposits, checks and withdrawals,<br>etc.) to match to the activity in the module. |
| Cash receipts/bank account<br>reconciliation reports | Through a report menu, the user must be able to<br>select/create reports produced by the system.<br>At a minimum, these reports include:<br>- Bank register<br>- Bank deposits<br>- Undeposited funds<br>- Electronic receipts register<br>- Unprocessed electronic receipts<br>- Reconciliation report |

<!-- page 57 -->
|  | - Cash receipts journal<br>- Recurring deposits |
| Transaction posting | The system should have the capability to process<br>transactions with a consideration of.<br>a) Effective date/ Value: the date from which<br>profit is calculated for a transaction (e.g., date of<br>the member deposit or withdrawal) for member<br>and facility accounts per transaction type, per<br>branch.<br>b) Transaction posting: generate receipts, check<br>vouchers, print passbook, print validation on<br>documents<br>c) The transactions should have a unique<br>identification code to differentiate different<br>nature of posting |
| Chart of Accounts | The System should have the ability to allow;<br>a) Sharing of accounts across multiple years<br>b) Possibility to allow for sorting of the chart of<br>accounts<br>c) Setting of financial periods<br>d) Flexibility to arrange/rearrange chart-of-accounts<br>structure.<br>e) Allow for multi-currency & multi-entity |
| Reports | The system should have the ability to provide reports<br>based on the following;<br>a) Standard GL reports, exporting of TBs per branch<br>and for the company.<br>b) Standard reporting for Assets and Liabilities as<br>per industry or IFRS9 requirement.<br>c) Can the reports be customized, and printed<br>demonstrate creating a custom report.<br>d) Executive reports, MIS Reports, Daily Business<br>Reports, Weekly, Monthly and Annual, Regulatory<br>reports (Best Practice).<br>e) At the minimum, we require summarized and<br>detailed daily statement of profit or loss, and<br>daily summarized and detailed statement of<br>financial position per branch, per segment, and<br>company.<br>f) Profitability and income report, per sector, per<br>staff, per branch per department.<br>g) Variance Analysis against budget<br>h) Report on member collection balances and<br>member accounts/facilities per sector, per<br>relationship officer, per branch, per region and<br>department. |
| Journal Entry | The system should have the ability to;<br>a) Query/View chart of account |

<!-- page 58 -->
|  | b) Populate warning alerts to users as set controls<br>(e.g., if exceed a Dr or Cr allowed limit set<br>threshold)<br>c) Restrict manual debits on income GLs |
| Closings | The system should have manual triggers to initiate;<br>a) Procedures to perform period end closing (Day,<br>Month, year)<br>b) Procedures to initialize P&L at year end<br>c) Procedures to initiate year-end processing at any<br>time after the end of the period and by<br>authorized person with such password rights<br>d) Minimum allowance for roll-back to post audit<br>entries before closure of year-end. |
| Prepayments for Expenses | I. Ability to maintain a prepayments schedule<br>Information required on the prepayments schedule<br>a. Description<br>b. Amount<br>c. Start Date<br>d. Duration<br>e. End Date<br>f. Monthly Expense<br>g. GL to DR<br>h. GL to CR<br>i. Total Expensed<br>j. Remaining Amount<br>II. Ability to automatically amortize the prepaid<br>amount monthly |
| Fixed Assets administration | I. Ability to maintain a fixed assets register<br>Information required on the Assets Register<br>a) Asset Category<br>b) Asset Number<br>c) Asset Name<br>d) Supplier<br>e) Asset Cost<br>f) Physical Location<br>g) Date of Purchase<br>h) No of Years<br>i) Rate of depreciation<br>j) End of Useful Life<br>k) Depreciation expense<br>l) Accumulated Depreciation<br>m) NBV<br>Ability to execute depreciation on a straight-line<br>method monthly at annual rates and starts after the |

<!-- page 59 -->

| purchase of the asset. If accounting policy ever<br>changes, the other depreciation models should be<br>available for customization.<br>II. Ability to initiate and post Depreciation of the<br>assets automatically every month end.<br>III. Ability to capture the following information:<br>a) Additions<br>b) Pre-payments<br>c) Work in progress<br>d) Revaluations<br>e) Disposals |
|---|

### Fixed Assets

Consider the below fixed assets categories and their respective depreciation rates:

| Asset Category | D e p r e c i a t i o n Y e a r s | Depreciation Rate |
|---|---|---|
| Office Equipment and Appliances | 2 | 50% |
| Furniture and fittings | 5 | 20% |
| Leasehold | 4 | 25% |
| Motor vehicles | 4 | 25% |
| Computer equipment | 3 | 33.3% |
| Intangible Assets | 4 | 25% |

### Inter Branch Accounts

Both member account transfers and GL transfer transactions will be supported between
branches through inter branch accounts.

|  | Requirement Subject |  | Requirement Description |
|---|---|---|---|
| Interbranch GL behaviors |  | All movement of funds between GL and interbranch GLs should<br>have a clear trail for audit of the transactions<br>The system should have an efficient way of transferring of staff<br>and loan portfolios across branches<br>The system should allow for efficient allocation of cost from<br>Central office and between branches where the costs are<br>incurred and expensed.<br>All interbranch loans should be tagged to the rightful<br>relationship officer even across branches.<br>Any mishaps on the main interbranch GL should only be<br>rectified by Finance<br>The system should allow for bulk reassigning of portfolios<br>between relationship officers in the event an officer leaves or is<br>moved to another branch. |  |

<!-- page 60 -->
The system should be branch based in the sequence below and should consider growth.

|  | Branch name |  | Branch Code |
|---|---|---|---|
| Central Office |  | 0 |  |
| Nairobi |  | 1 |  |
| Nakuru |  | 2 |  |
| Kiambu |  | 3 |  |
| Thika |  | 4 |  |
| Naivasha |  | 5 |  |
| Narok |  | 6 |  |
| Rongai |  | 7 |  |
| Kitengela |  | 8 |  |
| Meru |  | 9 |  |
| Kericho |  | 10 |  |
| Mombasa |  | 11 |  |
| Kariobangi |  | 12 |  |
| Nyeri |  | 13 |  |
| Eldoret |  | 14 |  |
| Kisumu |  | 15 |  |

We should be able to spool Trial balance, financial reports per branch as well as
consolidated for the company on an ad-hoc basis.

### Chart of Accounts

The GL and chart of accounts will be shared separately.

Provide for foreign currency GLs to cater for loans and borrowings incurred.

### Bonds/Treasury Bills and FX transactions

| Requirement Subject | Requirement Description |
|---|---|

<!-- page 61 -->
The system should have the capability of maintaining
investment bonds through the various accounts as below;

1. Investment in bonds-FVPL
2. Investment in bonds-HTM
Investment in bonds
3. Interest receivable on bonds
4. Interest income on bonds
5. Accrued interest purchased
6. Discount on bonds
7. Premium on bonds

| Investments in Treasury<br>bills | The system should have the capability of maintaining<br>investment bonds through the various accounts as below;<br>1. Investment in Treasury bills<br>2. Unrealized gain/loss account<br>3. Realized gain/loss account<br>4. Interest income on treasury bills |
|---|---|
| Foreign currency<br>transactions | We anticipate that there will be FX denominated loans. We<br>intend to mark them to market every end of month and<br>recognize the unrealized exchange profit/loss, and when<br>payments are done, to recognize the realized gain/loss.<br>Below are the accounts required<br>1. Realized exchange gains/losses-IS<br>2. Unrealized exchange gain/losses-IS |

## Funding

### Consideration

1. Short Term
2. Long Term

<!-- page 62 -->

### Private Placements -Features

| Product<br>Definition | Private placement Is an investment Offering by the Company offered<br>exclusively to clients as a private offer as defined in regulation 21 of the<br>Capital Markets. |
|---|---|
| Product<br>Features | • Interest rates are negotiable and is dependent on tenor of the<br>Placement<br>• Placement is booked for a year, but interest is dropped on member<br>collection account quarterly<br>• Investors can have unlimited receipts with different terms.<br>• Minimum offer amount of Placement is Ksh 100,000<br>• Maximum offer amount of Placement is Ksh 100 million<br>• Credit Interest is charged a withholding tax of 15% except for<br>customers who have tax exemption. |
| Rate of Return | Tenor (Month) Rate of Return<br>Up to 3 months 15%<br>Up to 6 months 16%<br>Up to 9 months 17%<br>1 year 18%<br>Above One Year 20%<br>Maximum interest rate booked is 20% |

| Requirement Subject | Requirement Description |
|---|---|
| Placement Registration | The system should have the ability to;<br>• Allow member information maintenance<br>• Allow member account approval (maker/Checker)<br>• Allow receipt of funds from bank account to member<br>account<br>• Allow booking of funds and assigning receipts |
| Placement Management | Placement management system capabilities<br>• Daily Interest accrual<br>• Placement is booked for a year, but interest is dropped<br>on member collection account monthly, quarterly,semi<br>annually,tri-annually,yearly<br>• Investor may choose to close placement receipt on<br>maturity.<br>• Notifications done on due dates<br>• Withholding capture<br>• Schedule monthly sending of placement statement to<br>investors via email. |

<!-- page 63 -->
|  | • Lien placement amount booked that has secured a loan<br>facility.<br>Should the customer choose to rollover the instructions, the<br>rollover instructions are:<br>• Renew Principal + interest – the outstanding principal is<br>to be rolled over with interest to a new placement<br>receipt.<br>• Renew Principal - Only the outstanding principal is to be<br>rolled over to a new placement receipt.<br>• Liquidate- Principal and interest accrued is posted to<br>member collection account.<br>• The interest accrued is paid to the customers member<br>collection account.<br>• No rollover – this is where the investor has not indicated<br>the rollover instructions. |
| Reports | • The system should avail below reports;<br>• All placement customers (static data)<br>• All active placements<br>• Active and closed receipts<br>• Matured placement<br>• Placement customers categories<br>• Withholding tax reports per customer<br>• Placement statement that shows the history of the<br>placement(roll-overs/liquidations)<br>• (See sample business request attached) |
| Placement product<br>categorization | Placement accounts are categorized into the below;<br>1. HNIs<br>2. Corporates<br>3. SACCOS<br>4. Investment Groups<br>5. Fund Managers<br>6. Insurance Companies<br>7. Churches<br>8. Financial Advisors<br>Each of these products should have a unique product code<br>that should be used during placement customer onboarding<br>such that the funds under each category can be identified<br>separately.<br>Note: Under the Financial Advisors product category, Each<br>advisor account under this category should have the ability<br>to have sub accounts of the customers they refer to be<br>onboarded which should be readily identifiable under that |

<!-- page 64 -->

| specific advisor portfolio, when the overall placement<br>register is accessed. |
|---|

### Private Placement Accounting Rules

**Daily accrual transaction posting flow**

- Cr: Interest Payable

- Dr: Interest Expense

**Monthly Withholding Tax Payable**

- Dr: Interest Payable

- Cr: Withholding Tax Payable

**Liquidation Instruction -(Break)**

- Cr: Member Collection account

- Dr: Placement account

- Cr: Withholding Tax

- Cr: Interest Payable

- Dr: Interest Expense

- Cr: Member Collection account

- Dr: Interest Payable

**Payment Voucher (to customer)**

- Cr: Bank account

- Dr: Member Collection account

**On Maturity – (Principal + Interest)**

- Cr: Member Collection account

- Dr: Placement account

- Cr: Member Collection account

<!-- page 65 -->
- Dr: Interest Payable

**Payment Voucher (to customer)**

- Cr: Bank account

- Dr: Member Collection account

**Payment Voucher (from customer)**

- Dr: Bank account

- Cr: Member Collection account

**Roll Over Instructions - (Principal + Interest)**

- Cr: Member Collection account

- Dr: Placement account

- Cr: Member Collection account

- Dr: Interest Payable

- Cr: Placement account

- Dr: Member Collection Payable

Note: Roll over (P) Consider above process

for roll over P+1 but include;

**Payment Voucher (to customer)**

- Cr: Bank account

- Dr: Member Collection account

Note: All entries in the system should have a clear way of getting the transaction trail for all
contra entries.

### Private Placement Glossary

| Instruction |  | Meaning |
|---|---|---|
| Placement maturity<br>instructions | 1. Transfer all to<br>member account | Client has requested to access all the funds<br>after maturity period, or they will give further<br>instructions thereafter. |
|  | 2. Renew principal | The client will access only the interest after<br>placement maturity, principal should roll over<br>for further period. |

<!-- page 66 -->
|  | 3. Renew Principal &<br>Interest | Client has requested not to access the interest<br>or the principal. All funds should roll over for a<br>further similar period under same terms. |
| Interest payment<br>instructions | 1. Weekly | The Interest to be paid weekly with weekly<br>principal rollover. |
|  | 2. Monthly | The interest to be paid monthly with principal<br>roll over |
|  | 3. Quarterly | The interest to be paid quarterly with principal<br>roll over |
|  | 4. Bi-Annual | Client accesses interest twice a year the<br>principal amount rolls over twice a year. |
|  | 5. Yearly | Client accesses the interest after one-year,<br>principal rolls over yearly. |
| Booking frequency | 30D | Interest is paid every 30 days |
|  | 90D | Interest is paid every 90 days |
|  | 91D | Interest is paid every 91 days |
|  | 182D | Interest is paid every 182 days |
|  | 210D | Interest is paid every 210 days |
|  | 365D | Interest is paid every after 365 days |
|  | other |  |

### Private Placement Report Templates

The System should be able to generate among others the below placement statements and
reports;

i. Member Placement report
ii. Member Placement statement
iii. Withholding Tax report
iv. Sector report

<!-- page 67 -->

## Long Term Borrowings

### Considerations

1. Term Loans from Financial Institutions e.g., banks
2. Venture funding

### Long Term funding accounting rules

**Recognize funds receipt**

- Dr: Bank

- Cr: Investor GL – Liability

**Interest accrual**

- Dr: Interest Expense

- Cr: Interest Payable – Liability

**Payment of Interest to Investor**

- Dr: Interest Payable

- Cr: Bank

- Cr: Withholding Tax

<!-- page 68 -->

## Risk and Audit

|  | Requirement Subject |  | Requirement Description |
|---|---|---|---|
| Risk and Audit |  | The system should have the capabilities of identifying and<br>mitigating risks relating to the core nature of the business<br>(Lending) aligned to;<br>i. Credit Risk<br>ii. Operational Risk<br>iii. Market Risk<br>iv. Liquidity Risk<br>a) The Risk Management Module should have the<br>capabilities to allow rating of customers, risk scoring,<br>loan loss indicator, liquidity barometer etc.<br>b) The system should offer centralized concept for limit<br>management at different levels (Maker/Checker), limit<br>interchange ability, collateral management, risk<br>management and exposure monitoring with tracking as<br>defined per set parameters by the risk officers. |  |
| AML |  | The system should have the capability to demonstrate the<br>following:<br>a) Profiling<br>b) Watchlist filtering/blacklisting members for various<br>reasons, e.g., fraudsters, serial defaulters, politically<br>exposed persons (PEP), tax-cheats, terrorism<br>financiers etc.<br>c) The system should have the capability to provide an<br>archive and storage of the blacklist which the audit<br>officers should be able to update during the normal<br>cause of business.<br>d) Transaction monitoring both broken and onerous that<br>meet declaration limit.<br>e) Detection of potentially suspicious activity<br>f) Alerts case management<br>g) Workflow and workflow violation in all modules<br>h) Reporting to designated emails on exceptions or<br>violations<br>i) Management reporting. |  |

<!-- page 69 -->

| Case Management<br>Module/Workflow | The system should have the capability to provide workflow<br>enquiries to show:<br>a) how many exceptions are outstanding at any given<br>time after being reported, this can restrict end of day<br>processes until solutions are provided.<br>b) who has responsibility for resolving them (as an alert<br>or pop up)<br>c) how long they have been outstanding<br>what their investigation status is (procedure on how to<br>resolve the issues)<br>d) An automated exception report from which a case may<br>be created is to be instigated. Allows for internal<br>incident reports to be lodged and tracking for<br>resolution.<br>e) The system is to accommodate a hierarchy of anti-<br>money laundering officers |
|---|---|
| Audit control | Logs<br>a) The solution should have the ability to record activities<br>on the entries and report by day, user, workstation<br>used for predetermined periods.<br>b) Error logs<br>c) Users viewing customer data<br>d) Accessed system utilities with username, time and<br>workstations<br>e) All maintenance activities<br>f) Logs should not be altered/editable<br>g) Access to classified accounts /GLs should relay alerts<br>to the executive<br>System Security<br>a) Security authorization-There should be a detailed<br>structure of authorization with ability to control access<br>to the CBS at the following levels<br>b) Control access to individual users and group of users<br>c) Control access to information in a particular functional<br>area e.g., certain accounts<br>d) Control the type of access at each of the level<br>described above: read only, create, update etc.<br>e) Solution that does NOT allow deletion of any<br>transaction-Whenever application is updated, the<br>original information should remain in the application as<br>an audit trail-The application should maintain<br>information on who made the changes and when.<br>Additionally<br>Ability to support an audit data mining tool-directly from<br>database. |

<!-- page 70 -->
| Compliance coding and<br>maintenance | a) Demonstrate ability to support transaction limit<br>monitoring capabilities (as defined for group of<br>customers, specific customer, account, products or<br>other user requirements)<br>b) Demonstrate ability to mark high risk accounts e.g.,<br>blacklisted & watchlist accounts, dormant accounts.<br>c) Demonstrate ability to monitor transactions affecting<br>sanctioned entities or individuals.<br>d) Demonstrate ability to maintain the sanction database<br>in the core banking system. The updates should<br>originate from a credible approved sanction list e.g. UN<br>Security Council (UNSC) list.<br>e) Allows updates (patches or comprehensive) for<br>compliance with additional regulations (both self &<br>industry) should the need arise. |

<!-- page 71 -->

## Information Technology

|  | Requirements Subject |  | Requirement Description |
|---|---|---|---|
| IT Department Functions |  | a) User Administration - User creation, Role center<br>personalization, granting of user role-based rights, Setup<br>and creation of workflows per function, activity and role.<br>Giving access to the system (Log in\Log out of users) |  |
|  |  | User\Functional Support - Gathering, analysis,<br>documentation, and issue resolution. Level I, Level II and<br>Level III support.<br>Coordination with system developers for level IV support. |  |
|  |  | b) Monitoring and configuring of system processes<br>and services -<br>-Ensuring automatic process/Manual (Interest billing and<br>posting & penalty billing and posting) are running.<br>-Email and SMS Services.<br>-Administering key services on windows server are<br>running.<br>c) Database Administration - Performing daily backups<br>and restoration.<br>Database optimization, Writing of SQL scripts to query<br>the database.<br>Creating and issuing of various reports<br>d) Core banking system policies enforcement - Security<br>i.e., Authorized access/access time, password policies,<br>Data policies (Role/function access)<br>e) User training – Performing periodic user training<br>(Knowledge transfer)<br>f) Documentation- System processes and functional<br>documentation. Creation of IT department training<br>manuals.<br>g) Audit trails - Performing of audit trails and analysis at<br>the system user interface level (Functional) and at the<br>database level for detection and systematic correction of<br>errors. |  |
| Merits to retain from old<br>system |  | • Availability of different system modules – Finance, Credit,<br>Member Registry, Private placement (FD) modules with<br>setups for each module. |  |
|  |  | • Ease of integration with alternate channels/third party<br>systems - Mobile Banking, SMS gateway, CRBs, others<br>include Cheque management and card management. |  |
|  |  | • Availability of system documentation and learning<br>materials online. |  |
|  |  | • Availability of highly customizable role centers. |  |
|  |  | • Availability of client-side audit trail functionality |  |
|  |  | • Availability of performance dash boards -Graphical charts<br>reporting and Business Intelligence reporting (Must be<br>configured by the developer) |  |

<!-- page 72 -->

|  | • Easy to export and save documents in various formats<br>word, excel, pdf and printing direct from the system. |
|---|---|
|  | • Clearly detailed system processes (Set to ready, set on<br>hold, Restart, Create reports and Log entries) |
|  | • Data classification capabilities (Sensitive, Personal,<br>Normal, Confidential) |
|  | • Availability of versioning which increases major bugs and<br>system security issues (Microsoft) |
|  | • Availability of automation capability and a manual<br>process as back up. |
|  | • Automated EOD, EOM, EOY processes. |
|  | • Policies enforcement i.e., data, passwords, and system<br>idle time. |
|  | • User intuitive interface and presentable GUI design. |
| Wishlist | Hardware, Software and Operating system specifications<br>-Storage requirements<br>-Back up requirements<br>-Requirements for the mirroring back up site |
|  | Primary data center and back up site requirements<br>Database applications (Oracle, MySQL Server)<br>Reporting services, (BI reporting), in-built reports, customizable<br>reports.<br>-Bandwidth requirements<br>The software should run over a WAN<br>IPSec VPN |
|  | Software requirements<br>The software should be able to use features of the specified<br>operating system(s)<br>The system should allow engineering, customizing and develop<br>new products and functional specifications/changes without or<br>with minimal coding<br>The system should have different modules (Fully integrated) i.e.<br>procurement Module, HR module, EDMS Module, Finance, Credit,<br>Operation, Registry, Administration and Fund Modules and<br>setups for each<br>-System should have the capability to monitor web-services,<br>application service and database services<br>- The system should be web enabled and have light desktop<br>applications to be installed on tablet devices<br>The system should have a query/reporting tool and BI<br>reporting.<br>The system should allow printing and use of standard printer<br>drivers<br>- Batch processing capabilities |

<!-- page 73 -->

| Databases and data management<br>- the system should use commercially available database such as<br>Oracle, MySQL Server (recommendations)<br>Database specifications e.g., Size<br>The system should support centralized processing i.e., branch,<br>agency and a mobile organizational structure<br>Availability of a test environment for any functional changes<br>before deployment to the production environment<br>- Database querying to manage system data, make changes,<br>resolve any issues. |
|---|
| Performance<br>Availability of tools that allows the bank to optimize, conduct<br>performance testing, including load and stress testing.<br>-Allow multiple concurrent access (What is the maximum)<br>Automated EOD, EOM and EOY processes<br>- Ability to mark pending transactions, flag any unbalanced<br>transactions during the above processes<br>- |
| Backup and Recovery<br>-Ability of the system to handle failure conditions and system<br>crashes (System based and server based)<br>Time to recover when connections are re-established<br>Internal transaction processing controls including the capability<br>in the event of a system failure the system should automatically<br>back out incompletely processed transactions, restore the<br>system to its last consistent state before the failure occurred<br>Restart capabilities for application's on-line and batch processing<br>components. |
| Security<br>-Data security controls on the system for data at rest, data on<br>transit or data transmissions.<br>Varying levels of update, view only, save only, add, approvals,<br>reviews and maker/checker capabilities.<br>-Audit trails of access and changes, record access activity, all log<br>in/log out /workstation/user/timestamp<br>-Transaction identification i.e. entry no. , document<br>no(journals/receipts), User ID and computer ID<br>- Submitted transactions/Initiated processes/direct<br>additions/modifications<br>-Password policies (8 characters minimum, no password reuse,<br>monthly password period, User initiated password change, no<br>remember of passwords, System Idle time, Multiple log in<br>restrictions )<br>- System ability to audit minimum requirements username,<br>branch, transaction date & time, Ip address, computer name,<br>department, browser<br>-Creation of user profiles/roles capabilities, independent control<br>for the creation/allocation of user rights/password<br>-Limitation of transaction amount per user input/authorize<br>definable at the product/account/role/user level<br>-Time based user access (User can only on weekdays, user |

<!-- page 74 -->
| locked out period - on leave)<br>-Maker/Checker on all transactions<br>-Control of printing of specific reports<br>-Encryption of passwords<br>-Versioning capability of the system (Upgrades/patching/bug<br>fixing)<br>- Restricted exporting/saving in different file formats<br>- Statements/documents customization to company standards<br>- Modules integrations/applications interoperability<br>- Mouse activated icons, buttons, scroll bars, drop down<br>lists(transaction level), check boxes, menu bars, Text boxes,<br>Resizable windows, restricted cut, copy and paste functions.<br>- Interoperability - APIs and Electronic Data Interchange (EDI)<br>Ability to hold API submitted transactions that do not pass<br>required edits in suspense pending appropriate corrective actions<br>by user. suspense processing must include the ability to view,<br>update or delete suspended transactions, automatically re-<br>process suspended transactions i.e., M-Pesa<br>-Alternate channels Mobile banking, internet banking, cards. |
| Workflows/Messaging<br>-Create workflows per department, user groups, function,<br>Process at approval levels. Definitions of multiple levels of<br>document approvals based on a defined criteria including<br>amounts, items, document types. Ability to track approval<br>events time/date and approving party.<br>- Messaging and notifications i.e., warning messages, feedbacks,<br>notifications<br>- Emailing/SMS notifications and capabilities externally and<br>internally i.e., pending transactions/approvals<br>- Reports for external emails Audit capabilities sent emails/failed<br>/pending |
| Automated processes<br>- Scheduling capabilities to initiate, monitor, pause and stop<br>scheduled processes. Reports and log files for each report per<br>function and per department.<br>-Alternative back up/ manual processes for the automated<br>processes. |

<!-- page 75 -->
| Reporting<br>-System ability to export data in different formats (Excel, CSV,<br>PDF, Word)<br>-System report scheduling<br>-Design and report writer functionalities, drag and drop<br>-Built in standard reports<br>-MIS reporting and profitability graphs |
| Ease of Use<br>- Data validation for valid date fields, birthdates, minimum and<br>maximum values, mandatory fields<br>Notifications, warnings i.e., pop ups<br>user tutorial, manuals and documentation<br>Trainings - Onsite/Offsite |
| Vendor support and technical assistance<br>24/7 online support<br>On Premise support<br>Documentation of issues raised, resolved (Emails and other<br>platforms) for reference and tracking<br>- Availability of issue resolution matrix (Factors considered),<br>Timelines for issue resolution. |

## Integrations

|  | Requirement Subject |  | Requirement Description |
|---|---|---|---|
| 3rd Party Integrations |  | We expect that the below existing systems will be integrated<br>with the core banking system<br>I. M-Pesa Paybills C2B<br>II. SMS Gateway<br>III. M-Pesa transaction receipts. |  |

<!-- page 76 -->
A test on all API integrations should be conducted to confirm
that;
i. application endpoints and data sharing functions work
as expected
ii. junk data/test data does not enter the main database
and create application problems or data corruption
iii. all application functions across all platforms, including
Integration Requirement
desktop, web or mobile as per the business
requirement
iv. data feeds from the various integrated systems are
sent as expected to the desired locations/ repositories.
v. Data access and security is as expected.

A sign off on this from the related parties will be expected.

## Static Data Migration

This process will entail migration of active customers’ data and balances only.

1. The agreed historical data cutoff date for migration and data will be moved with effect at
an agreed date and time based on the kickoff meeting between the Company and Eazzy
Books.
2. The Core banking vendor will move client data which will include but not limited to:
a) All open accounts with their respective closing balances as at the agreed date during
the kickoff meeting
b) Customer KYC information associated with the customers and accounts moved. This
includes account images, reminders, operation mandate, special condition etc.
c) System products, product features and the tariff settings. Charges will be created
afresh.
d) Loan parameters
e) Transaction balances for customer and general ledger statement as the agreed date
during the kickoff meeting
f) GL numbers and grouping shall not change. (See Chart of Accounts)
g) Client number shall be regenerated to an incremental running number of 11 digits that
contains branch code, product code and the customer number.
h) Charges parameters as per the product settings should be considered.
i) Charges: All other system charges should be held in lien and charged when the account
gets funded for instance ledger fee, minimum fee, cheque books etc.

## Migration Audit

After a successful data migration, we will conduct data audit; the audit shall aim at
determining the following:

<!-- page 77 -->
- Correct customer data have been migrated. This includes customer balances, record
count, and client information and account details.
- General ledger accounts and balance are correctly migrated. All general ledger accounts
shall be included in all branches.
- Validation of loan balances per account and migrated from (Insert previous CBS) to Eazzy
Books and also the regenerated schedules.
- Proper mapping of products to retain the current product features
- Any other needed data audit shall be done.

## Reports

Additional report as per the business request should be easily availed on need basis.

The system should dump selected reports after system closure and start of day at a
designated folder for access. The reports include loan list, Trial balance, member list, PAR
report & funding department reports.

### Credit Department List of Reports

1. Loan List
2. Loan details Analysis – PAR
3. Loan repayments
4. Collateral listing

All reports to be per individual, branch, segment & company

### SMS Templates

Disbursement SMS
Dear client name, Your loan of Ksh……… has been disbursed. Thank you for choosing us.

<!-- page 78 -->
Loan Repayment SMS
Dear client name, your loan is due payment in 7 days, kindly purpose to clear before the due
date. For queries call 07xx xxx xxx.
Dear client name, your loan is due for payment today, kindly clear as agreed. For queries call
07xx xxx xxx.
Dear client name, your loan is in arrears of Ksh 92,253. Pay today to avoid penalties. For
queries call 07xx xxx xxx.
Dear client name, your loan is in arrears and continues to attract a penalty of 5%, purpose to
clear the arrears.
Dear client name, your has been in arrears over three months now, note that failure to clear
the arrears, we shall proceed to advertise and dispose the vehicle without any further
reference to you in the next 14 days. For queries call 07xx xxx xxx.

Insurance Expiry SMS
Dear client name, Comprehensive insurance for KAA 001A expires in 30 days, make plans to
have it renewed. For queries call 072xxxxxxxxx

### Investor Relations Department List of reports

1. Placement register
2. Placement report
3. Savings Report
4. Withholding Tax register
5. Email alert to placement teams group email on placements falling due

#### Private Placement Email notification

Email: Investments@xxxxx.co.ke

Subject: Private Placement eStatement as at December 31, 2021

Dear Bancy,

We sincerely thank you for your continued business support.

Please find attached your private placement eStatement as at December 31, 2025

For any clarification, please contact your Relationship Manager or the below contacts

Email: investments@xxxxx.co.ke

<!-- page 79 -->
Phone:07xx xxx xxx

Thank You

### Finance Department List of Reports

1. Balance Sheet
2. Income Statement
3. Trial Balance
4. Commission Payment
5. Revenue Assurance Report

## Report Templates

(See annexures)

<!-- page 80 -->
