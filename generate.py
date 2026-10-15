"""Deterministic synthetic CRM, marketing and partner transactions."""

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker


def generate(out, count=10000, seed=42):
    """Create related source records plus two known defects for reconciliation.

    The separate random generators keep application choices reproducible without
    changing Faker's global state. Random-call order is intentional: changing it
    changes the seeded sample and its recorded validation results.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed)

    def save(name, fields, rows):
        with (out / (name + ".csv")).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    # Partner rates and rep quotas are explicit demo policies, not inferred facts.
    partners = [
        dict(partner_id=i, company=fake.company(), commission_rate=rate)
        for i, rate in enumerate(
            [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.05, 0.06, 0.07, 0.08], 1
        )
    ]
    campaigns = [
        dict(campaign_id=i, channel=channel, spend=10000 + i * 1000)
        for i, channel in enumerate(["Email", "Search", "Partner event", "Webinar"], 1)
    ]
    leads = []
    sales = []
    customers = []
    tickets = []
    reps = [
        dict(
            rep_id=i,
            name=fake.name(),
            monthly_quota=1500000,
            base_rate=0.02,
            accelerator_rate=0.04,
        )
        for i in range(1, 6)
    ]
    for i in range(1, count + 1):
        campaign = rng.choice(campaigns)
        partner = rng.choice(partners)
        created = date(2025, 1, 1) + timedelta(days=rng.randrange(300))
        # Give campaigns different conversion tendencies so the model has a
        # weak signal; this is not evidence of real campaign effectiveness.
        won = rng.random() < (0.15 + 0.05 * campaign["campaign_id"])
        leads.append(
            dict(
                lead_id=i,
                company=fake.company(),
                contact_email=f"contact{i}@example.test",
                campaign_id=campaign["campaign_id"],
                partner_id=partner["partner_id"],
                rep_id=1 + (i % 5),
                region=["Americas", "EMEA", "APAC"][i % 3],
                created_date=created,
                status="Won" if won else "Open",
                employee_count=rng.randint(10, 5000),
            )
        )
        if won:
            amount = rng.randrange(1000, 100001)
            refund = rng.choice([0, 0, 0, 0, round(amount * 0.2, 2)])
            commission = round((amount - refund) * partner["commission_rate"], 2)
            # Some partners have booking errors; others have unpaid but
            # reconciled accruals so both finance workflow paths can be exercised.
            sales.append(
                dict(
                    sale_id=i,
                    lead_id=i,
                    sale_date=created + timedelta(days=rng.randint(1, 30)),
                    gross_amount=amount,
                    refund_amount=refund,
                    booked_commission=round(
                        commission
                        + (100 if i % 17 == 0 and partner["partner_id"] <= 5 else 0),
                        2,
                    ),
                    paid_commission=(
                        round(commission + (100 if i % 17 == 0 else 0), 2)
                        if partner["partner_id"] <= 5
                        else 0
                    ),
                )
            )
    # Only converted leads become customers. Support is generated separately
    # so ticket counts do not determine sales or the model's target.
    for sale in sales:
        customers.append(
            dict(
                customer_id=sale["lead_id"],
                lead_id=sale["lead_id"],
                region=["Americas", "EMEA", "APAC"][sale["lead_id"] % 3],
                onboard_days=rng.randint(1, 25),
            )
        )
        if rng.random() < 0.35:
            opened = sale["sale_date"] + timedelta(days=rng.randint(1, 15))
            hours = rng.randint(1, 96)
            tickets.append(
                dict(
                    ticket_id=sale["sale_id"],
                    customer_id=sale["lead_id"],
                    opened_date=opened,
                    resolution_hours=hours,
                    csat=5 if hours < 24 else (3 if hours < 48 else 1),
                    category=rng.choice(["Onboarding", "Billing", "Technical"]),
                )
            )
    save("reps", list(reps[0]), reps)
    save("customers", list(customers[0]), customers)
    save("tickets", list(tickets[0]), tickets)
    save("partners", list(partners[0]), partners)
    save("campaigns", list(campaigns[0]), campaigns)
    save("leads", list(leads[0]), leads)
    save("sales", list(sales[0]), sales)
    # Controlled defects: one duplicate key and one invalid financial record.
    bad = dict(sales[0])
    bad.update(sale_id=count + 1, gross_amount=-10, refund_amount=0)
    with (out / "sales.csv").open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sales[0]), lineterminator="\n")
        w.writerows([sales[0], bad])
    return {"leads": len(leads), "valid_sales": len(sales), "injected_defects": 2}


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--out", default="data/raw")
    a.add_argument("--leads", type=int, default=10000)
    args = a.parse_args()
    if args.leads < 100:
        a.error("--leads must be at least 100")
    print(generate(args.out, args.leads))
