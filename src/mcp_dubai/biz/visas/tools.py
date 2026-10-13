"""visas tool functions."""

from __future__ import annotations

from typing import Any, Final

from mcp_dubai._shared.knowledge import register_domain_knowledge
from mcp_dubai._shared.schemas import KnowledgeMetadata, ToolResponse
from mcp_dubai.biz._data.loader import extract_knowledge, load_data_file

_DATA = load_data_file("visas.json")
KNOWLEDGE: KnowledgeMetadata = extract_knowledge(_DATA)
register_domain_knowledge("visas", KNOWLEDGE)


def _all_visas() -> list[dict[str, Any]]:
    items = _DATA.get("visas", [])
    return list(items) if isinstance(items, list) else []


# USD/AED is a hard peg; the CBUAE reference rate is 3.6725 AED per USD.
AED_PER_USD: Final[float] = 3.6725

# GDRFA Dubai Virtual Working Programme: minimum USD 3,500 monthly income.
# Compared in AED so the boundary is exact rather than float-divided.
_VIRTUAL_WORKING_MIN_USD: Final[int] = 3500
_VIRTUAL_WORKING_MIN_AED: Final[float] = _VIRTUAL_WORKING_MIN_USD * AED_PER_USD  # 12853.75

# Green Visa freelancer track: AED 360,000 annual income in EACH of the prior
# two years, not AED 360,000 cumulative across both.
_GREEN_FREELANCER_MIN_ANNUAL_AED: Final[int] = 360_000

# Golden Visa entrepreneur (ICP page updated 2026-09-10): annual revenue of a
# UAE SME, or the total sale value of prior ventures. These replaced the old
# AED 500,000 project-valuation test.
_GOLDEN_ENTREPRENEUR_MIN_REVENUE_AED: Final[int] = 1_000_000
_GOLDEN_ENTREPRENEUR_MIN_EXIT_AED: Final[int] = 7_000_000

VALID_PROFILES = {
    "founder",
    "salaried_employee",
    "freelancer",
    "remote_worker",
    "investor",
    "real_estate_investor",
    "specialized_talent",
    "spouse_or_dependent",
    "retiree",
    "tourist",
}


async def list_visa_types() -> dict[str, object]:
    """List every UAE visa type in the curated dataset."""
    visas = _all_visas()
    return (
        ToolResponse[dict[str, object]]
        .ok(
            {
                "count": len(visas),
                "visas": [
                    {
                        "id": v.get("id"),
                        "name": v.get("name"),
                        "track": v.get("track"),
                        "duration_label": v.get("duration_label"),
                    }
                    for v in visas
                ],
            },
            knowledge=KNOWLEDGE,
        )
        .model_dump()
    )


async def visa_details(visa_id: str) -> dict[str, object]:
    """Return the full curated record for a single visa type by id."""
    if not visa_id:
        return ToolResponse[dict[str, object]].fail(error="visa_id must not be empty").model_dump()

    needle = visa_id.strip().lower()
    for visa in _all_visas():
        if str(visa.get("id", "")).lower() == needle:
            return ToolResponse[dict[str, object]].ok(visa, knowledge=KNOWLEDGE).model_dump()

    valid_ids = sorted(str(v.get("id", "")) for v in _all_visas())
    return (
        ToolResponse[dict[str, object]]
        .fail(error=f"Unknown visa_id {visa_id!r}. Valid: {valid_ids}")
        .model_dump()
    )


async def visa_recommend(
    profile: str,
    monthly_salary_aed: int | None = None,
    annual_income_aed: int | None = None,
    has_uae_employer: bool = False,
    has_uae_trade_license: bool = False,
    age: int | None = None,
    duration_years_min: int | None = None,
) -> dict[str, object]:
    """Recommend a UAE visa type for a given founder/employee profile."""
    if profile not in VALID_PROFILES:
        return (
            ToolResponse[dict[str, object]]
            .fail(error=(f"profile must be one of {sorted(VALID_PROFILES)}, got {profile!r}"))
            .model_dump()
        )
    if monthly_salary_aed is not None and monthly_salary_aed < 0:
        return (
            ToolResponse[dict[str, object]]
            .fail(error=f"monthly_salary_aed must be >= 0, got {monthly_salary_aed}")
            .model_dump()
        )
    if annual_income_aed is not None and annual_income_aed < 0:
        return (
            ToolResponse[dict[str, object]]
            .fail(error=f"annual_income_aed must be >= 0, got {annual_income_aed}")
            .model_dump()
        )
    if duration_years_min is not None and duration_years_min < 0:
        return (
            ToolResponse[dict[str, object]]
            .fail(error=f"duration_years_min must be >= 0, got {duration_years_min}")
            .model_dump()
        )
    if age is not None and age < 0:
        return (
            ToolResponse[dict[str, object]].fail(error=f"age must be >= 0, got {age}").model_dump()
        )

    candidates: list[dict[str, Any]] = []
    reasoning: list[str] = []
    warnings: list[str] = []

    visas = _all_visas()
    by_id = {str(v.get("id", "")): v for v in visas}

    def _add(visa_id: str, why: str) -> None:
        v = by_id.get(visa_id)
        if v is not None:
            if duration_years_min is not None:
                duration = v.get("duration_years")
                if not isinstance(duration, (int, float)) or duration < duration_years_min:
                    return
            candidates.append(
                {
                    "id": v.get("id"),
                    "name": v.get("name"),
                    "track": v.get("track"),
                    "duration_label": v.get("duration_label"),
                    "why": why,
                }
            )

    if profile == "founder":
        if has_uae_trade_license:
            _add(
                "investor_partner",
                "You hold a UAE trade license, so the Investor / Partner Visa is the standard founder route (2-year residence).",
            )
        if monthly_salary_aed and monthly_salary_aed >= 30000:
            _add(
                "golden_specialized_talent",
                "AED 30,000+ monthly salary meets the skilled-professional salary screening threshold; UAE employment, qualifications and other conditions still apply.",
            )
        _add(
            "golden_entrepreneur",
            "Founders of a UAE SME with AED 1,000,000+ annual revenue, or with prior exits totalling AED 7,000,000+, can apply for the 10-year Golden Visa entrepreneur category.",
        )

    elif profile == "salaried_employee":
        if has_uae_employer:
            _add("employment", "Standard 2-year Employment Visa, sponsored by your UAE employer.")
        if monthly_salary_aed and monthly_salary_aed >= 15000:
            _add(
                "green_skilled_employee",
                "AED 15,000+ monthly salary meets the Green Visa skilled-employee salary threshold (5-year, self-sponsored), subject to employment and qualification requirements.",
            )
            warnings.append(
                "Green Visa requires MOHRE skill level 1, 2, or 3 plus a bachelor's degree."
            )
        if monthly_salary_aed and monthly_salary_aed >= 30000:
            _add(
                "golden_specialized_talent",
                "AED 30,000+ monthly salary may support the Golden Visa skilled-professional route, subject to all other conditions.",
            )

    elif profile == "freelancer":
        _add(
            "freelance_permit",
            "Start with a Freelance Permit (TECOM, GoFreelance, or other free zone freelance program). 1 to 2 years.",
        )
        if annual_income_aed and annual_income_aed >= _GREEN_FREELANCER_MIN_ANNUAL_AED:
            _add(
                "green_freelancer",
                "AED 360,000 annual freelance income in each of the prior 2 years qualifies for the Green Visa freelancer track (5-year, self-sponsored).",
            )

    elif profile == "remote_worker":
        if monthly_salary_aed and monthly_salary_aed >= _VIRTUAL_WORKING_MIN_AED:
            _add(
                "virtual_working",
                "USD 3,500+ monthly salary from a foreign employer qualifies for the Virtual Working Programme (1-year UAE residency).",
            )
        else:
            _add(
                "virtual_working",
                "Virtual Working Programme requires USD 3,500+ monthly salary from a foreign employer.",
            )

    elif profile == "investor":
        _add(
            "investor_partner", "Investor / Partner Visa (2 years), linked to a UAE trade license."
        )
        _add(
            "golden_entrepreneur",
            "Golden Visa entrepreneur category (10 years) for a UAE SME with AED 1,000,000+ annual revenue or prior exits totalling AED 7,000,000+.",
        )

    elif profile == "real_estate_investor":
        _add(
            "golden_investor_real_estate",
            "Real estate worth AED 2 million or more can qualify for the 10-year Golden Visa, including approved-bank mortgaged or approved-developer off-plan property.",
        )
        _add(
            "property_investor_2yr",
            "Below AED 2M, Dubai's 2-year Property Investor Visa is the fallback: "
            "the AED 750,000 minimum was removed for sole owners in April 2026 "
            "(any completed Dubai residential property can qualify, subject to "
            "the usual conditions); co-owners need a registered share of at "
            "least AED 400,000 each.",
        )

    elif profile == "specialized_talent":
        _add(
            "golden_specialized_talent",
            "Exceptional-talent categories have specific nomination or qualification rules. The skilled-professional route requires AED 30,000+ monthly salary; GDRFA lists 6 months of bank salary transfers.",
        )

    elif profile == "spouse_or_dependent":
        _add(
            "family_dependent", "Family / Dependent Visa, linked to your sponsor's residence visa."
        )
        warnings.append(
            "Sponsor minimum salary: AED 4,000, or AED 3,000 plus employer-provided "
            "accommodation. Confirm acceptable income evidence with the issuing "
            "authority. Marriage and birth certificates must be attested."
        )

    elif profile == "retiree":
        if age is not None and age >= 55:
            _add(
                "retirement",
                "Retirement Visa (5 years). Requires 15+ years worked, then EITHER "
                "AED 1M property AND AED 1M savings (both), OR annual income of "
                "AED 240,000 for Dubai applications (AED 180,000 federal).",
            )
            warnings.append(
                "The property and savings amounts are cumulative, not alternatives. "
                "The 15-year work history is a separate mandatory requirement."
            )
        else:
            warnings.append("Retirement Visa requires age 55 or older.")

    elif profile == "tourist":
        _add("tourist_60", "60-day Tourist Visa for longer scoping trips.")
        _add("tourist_30", "30-day Tourist Visa for short scoping trips.")

    if not candidates:
        warnings.append(
            "No recommendation matched this profile and the supplied numbers. "
            "Use list_visa_types() to browse all options."
        )

    reasoning.append(
        "Recommendations are derived from the curated visas dataset. "
        "Verify final requirements with ICP, GDRFA Dubai, or Amer."
    )

    return (
        ToolResponse[dict[str, object]]
        .ok(
            {
                "profile": profile,
                "candidates": candidates,
                "reasoning": reasoning,
                "warnings": warnings,
                "inputs": {
                    "monthly_salary_aed": monthly_salary_aed,
                    "annual_income_aed": annual_income_aed,
                    "has_uae_employer": has_uae_employer,
                    "has_uae_trade_license": has_uae_trade_license,
                    "age": age,
                    "duration_years_min": duration_years_min,
                },
            },
            knowledge=KNOWLEDGE,
        )
        .model_dump()
    )


async def golden_visa_check(
    monthly_salary_aed: int | None = None,
    real_estate_value_aed: int | None = None,
    project_value_aed: int | None = None,
    annual_revenue_aed: int | None = None,
    prior_exit_value_aed: int | None = None,
) -> dict[str, object]:
    """Screen supplied financial thresholds; this does not determine visa eligibility."""
    for name, value in (
        ("monthly_salary_aed", monthly_salary_aed),
        ("real_estate_value_aed", real_estate_value_aed),
        ("project_value_aed", project_value_aed),
        ("annual_revenue_aed", annual_revenue_aed),
        ("prior_exit_value_aed", prior_exit_value_aed),
    ):
        if value is not None and value < 0:
            return (
                ToolResponse[dict[str, object]]
                .fail(error=f"{name} must be >= 0, got {value}")
                .model_dump()
            )
    eligible: list[dict[str, str]] = []
    not_eligible: list[dict[str, str]] = []
    notes: list[str] = []

    if monthly_salary_aed is not None:
        if monthly_salary_aed >= 30000:
            eligible.append(
                {
                    "category": "specialized_talent",
                    "criterion": (
                        "AED 30,000+ monthly salary meets the skilled-professional "
                        "salary threshold. GDRFA lists 6 months of salary transfers; "
                        "UAE employment, qualifications and other conditions still apply."
                    ),
                }
            )
        else:
            not_eligible.append(
                {
                    "category": "specialized_talent",
                    "criterion": (
                        f"The skilled-professional salary threshold is AED 30,000+ "
                        f"monthly. Have AED {monthly_salary_aed}. Other exceptional-"
                        "talent categories may use nomination-based criteria."
                    ),
                }
            )

    if real_estate_value_aed is not None:
        if real_estate_value_aed >= 2000000:
            eligible.append(
                {
                    "category": "real_estate_investor",
                    "criterion": (
                        "AED 2,000,000+ in UAE property. ICP and GDRFA accept "
                        "property mortgaged with an approved bank or bought "
                        "off-plan from an approved developer; neither states a "
                        "minimum paid-in share, so confirm the evidence (DLD "
                        "certificate, bank letter) with GDRFA/ICP."
                    ),
                }
            )
        else:
            not_eligible.append(
                {
                    "category": "real_estate_investor",
                    "criterion": (
                        f"Need AED 2,000,000+ in property. Have AED {real_estate_value_aed}. "
                        "Consider Dubai's 2-year Property Investor Visa instead: the "
                        "minimum value was removed for sole owners in April 2026 "
                        "(AED 400,000 share per co-owner for joint ownership)."
                    ),
                }
            )

    entrepreneur_met: list[str] = []
    entrepreneur_short: list[str] = []
    if annual_revenue_aed is not None:
        if annual_revenue_aed >= _GOLDEN_ENTREPRENEUR_MIN_REVENUE_AED:
            entrepreneur_met.append(
                "UAE SME annual revenue of AED 1,000,000+ meets the ICP threshold, "
                "subject to approval of the venture by an accredited incubator, "
                "the Ministry of Economy or a relevant local authority."
            )
        else:
            entrepreneur_short.append(
                f"ICP requires UAE SME annual revenue of AED 1,000,000+. "
                f"Have AED {annual_revenue_aed}."
            )
    if prior_exit_value_aed is not None:
        if prior_exit_value_aed >= _GOLDEN_ENTREPRENEUR_MIN_EXIT_AED:
            entrepreneur_met.append(
                "Prior ventures sold for a total of AED 7,000,000+ meets the ICP "
                "founder-exit threshold."
            )
        else:
            entrepreneur_short.append(
                f"ICP requires prior ventures sold for a total of AED 7,000,000+. "
                f"Have AED {prior_exit_value_aed}."
            )
    if entrepreneur_met:
        eligible.append(
            {
                "category": "entrepreneur",
                "criterion": (
                    " ".join(entrepreneur_met) + " Dubai's GDRFA route instead uses a "
                    "Dubai Future Foundation nomination with its own income tests."
                ),
            }
        )
    elif entrepreneur_short:
        not_eligible.append({"category": "entrepreneur", "criterion": " ".join(entrepreneur_short)})
    if project_value_aed is not None:
        notes.append(
            "project_value_aed is no longer screened: ICP replaced the AED 500,000 "
            "project-valuation test with AED 1,000,000 annual SME revenue or AED "
            "7,000,000 in prior exits. Pass annual_revenue_aed or prior_exit_value_aed."
        )

    return (
        ToolResponse[dict[str, object]]
        .ok(
            {
                "any_eligible": len(eligible) > 0,
                "assessment_scope": "Financial threshold screening only; not final visa eligibility.",
                "requires_authority_approval": True,
                "eligible": eligible,
                "not_eligible": not_eligible,
                "notes": notes,
                "inputs": {
                    "monthly_salary_aed": monthly_salary_aed,
                    "real_estate_value_aed": real_estate_value_aed,
                    "project_value_aed": project_value_aed,
                    "annual_revenue_aed": annual_revenue_aed,
                    "prior_exit_value_aed": prior_exit_value_aed,
                },
            },
            knowledge=KNOWLEDGE,
        )
        .model_dump()
    )
