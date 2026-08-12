# 09. Financial Profile Schema

## Goal
나이/직업/소득/자산/부채/목표 등 사용자 상황을 고려하되 불필요한 개인정보는 수집하지 않는다.

## MVP profile
### Demographic / household
- age_band
- employment_status
- household_size
- dependents_count
- marital_status (optional)
- region (정책 eligibility에 필요할 때만)

### Income / cashflow
- monthly_net_income
- monthly_fixed_expenses
- monthly_variable_expenses
- liquid_assets
- emergency_fund_target_months

### Debt
- total_debt
- monthly_debt_payment
- loan_items[]: category, balance, annual_rate, remaining_months, repayment_type

### Credit / eligibility
- credit_score_band
- business_owner
- business_age_months
- annual_business_revenue_band

### Goal
housing, emergency_cash, debt_refinance, living_expense, startup/business, vehicle, asset_building, other

## Derived metrics
- disposable cashflow = income - fixed - variable - debt payment
- service-specific debt payment ratio = debt payment / income
- emergency fund coverage = liquid assets / essential monthly expense

공식 DSR과 동일하다고 표시하지 않는다. 필요 시 공식 규칙을 별도 구현한다.

## Design notes
- 성별은 실제 eligibility/UX 근거가 있을 때만 사용한다.
- 주민번호, 계좌번호, 실명은 MVP에서 받지 않는다.
- exact age/credit score보다 band 우선.
- 어떤 profile field가 결정에 사용됐는지 audit 가능하게 한다.
