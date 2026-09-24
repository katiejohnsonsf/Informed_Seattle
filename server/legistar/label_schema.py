"""
Taxonomy constants for the Council Bill labeling schema (v0.1).

Facets:
  0 - Triage (record_class, resident_salient)
  1 - Topic (policy_area)
  2 - Affected groups (statutory_populations, constituencies)
  3 - Stakes (relation, valence, directness, confidence, participation_window)
"""

# ── Facet 0: Triage ──────────────────────────────────────────────────────────

RECORD_CLASSES = [
    "policy",
    "appointment",
    "property_transaction",
    "contract_authorization",
    "budget_technical",
    "honorific",
    "quasi_judicial",
    "other_administrative",
]

RECORD_CLASS_LABELS = {
    "policy": "Policy",
    "appointment": "Appointment",
    "property_transaction": "Property Transaction",
    "contract_authorization": "Contract Authorization",
    "budget_technical": "Budget/Technical",
    "honorific": "Honorific",
    "quasi_judicial": "Quasi-Judicial",
    "other_administrative": "Other Administrative",
}

# ── Facet 1: Topic ────────────────────────────────────────────────────────────

POLICY_AREAS = [
    "housing-and-tenancy",
    "land-use-and-zoning",
    "transportation-and-streets",
    "transit",
    "public-safety-and-policing",
    "criminal-legal-system",
    "homelessness-and-shelter",
    "parks-open-space-and-recreation",
    "water-sewer-and-drainage",
    "electricity-and-energy",
    "environment-and-climate",
    "public-health",
    "human-services-and-food-security",
    "education-and-youth",
    "arts-and-culture",
    "economic-development-and-small-business",
    "labor-and-workforce-standards",
    "civil-rights-and-anti-discrimination",
    "taxes-and-revenue",
    "budget-and-appropriations",
    "city-property-and-real-estate",
    "contracts-procurement-and-franchises",
    "governance-elections-and-ethics",
    "technology-data-and-privacy",
    "emergency-management",
    "animals-and-nuisance",
]

POLICY_AREA_LABELS = {
    "housing-and-tenancy": "Housing & Tenancy",
    "land-use-and-zoning": "Land Use & Zoning",
    "transportation-and-streets": "Transportation & Streets",
    "transit": "Transit",
    "public-safety-and-policing": "Public Safety & Policing",
    "criminal-legal-system": "Criminal Legal System",
    "homelessness-and-shelter": "Homelessness & Shelter",
    "parks-open-space-and-recreation": "Parks, Open Space & Recreation",
    "water-sewer-and-drainage": "Water, Sewer & Drainage",
    "electricity-and-energy": "Electricity & Energy",
    "environment-and-climate": "Environment & Climate",
    "public-health": "Public Health",
    "human-services-and-food-security": "Human Services & Food Security",
    "education-and-youth": "Education & Youth",
    "arts-and-culture": "Arts & Culture",
    "economic-development-and-small-business": "Economic Development & Small Business",
    "labor-and-workforce-standards": "Labor & Workforce Standards",
    "civil-rights-and-anti-discrimination": "Civil Rights & Anti-Discrimination",
    "taxes-and-revenue": "Taxes & Revenue",
    "budget-and-appropriations": "Budget & Appropriations",
    "city-property-and-real-estate": "City Property & Real Estate",
    "contracts-procurement-and-franchises": "Contracts, Procurement & Franchises",
    "governance-elections-and-ethics": "Governance, Elections & Ethics",
    "technology-data-and-privacy": "Technology, Data & Privacy",
    "emergency-management": "Emergency Management",
    "animals-and-nuisance": "Animals & Nuisance",
}

# ── Facet 2a: Statutory populations ──────────────────────────────────────────

STATUTORY_POPULATIONS = [
    "racial-or-ethnic-minorities",
    "low-income-populations",
    "linguistically-isolated",
    "people-with-disabilities",
    "older-adults",
    "youth-and-children",
    "pregnant-people-and-new-parents",
    "workers-in-affected-industries",
    "tribal-members-and-treaty-rights-holders",
    "populations-facing-environmental-harm",
    "overburdened-community-geography",
]

STATUTORY_POPULATION_LABELS = {
    "racial-or-ethnic-minorities": "Racial or Ethnic Minorities",
    "low-income-populations": "Low-Income Populations",
    "linguistically-isolated": "Linguistically Isolated (LEP)",
    "people-with-disabilities": "People with Disabilities",
    "older-adults": "Older Adults",
    "youth-and-children": "Youth & Children",
    "pregnant-people-and-new-parents": "Pregnant People & New Parents",
    "workers-in-affected-industries": "Workers in Affected Industries",
    "tribal-members-and-treaty-rights-holders": (
        "Tribal Members & Treaty Rights Holders"
    ),
    "populations-facing-environmental-harm": "Populations Facing Environmental Harm",
    "overburdened-community-geography": "Overburdened Community Geography",
}

# Data dictionary: precise definitions grounded in either a real Census/ACS
# variable or, where no ACS variable exists, the composite dataset actually
# used to identify that population. These are surfaced as reader-facing
# tooltips and also fed into the labeling prompt so the model classifies
# against a fixed definition rather than guessing at one from the slug name.
#
# None of these are literal Title VI (race/color/national-origin) categories
# except the first — the rest draw on separate statutes (ADA, Age
# Discrimination Act), tribal treaty law, or environmental-justice practice.
# The EO 12898 environmental-justice framework and the EO 13166 LEP guidance
# this list echoes were both rescinded by the federal government in early
# 2025; the ACS variables themselves are unaffected and remain current.
STATUTORY_POPULATION_DEFINITIONS = {
    "racial-or-ethnic-minorities": (
        "People identifying as a race or ethnicity other than non-Hispanic "
        "White alone (Census race / Hispanic-origin categories, ACS Table "
        "B03002) — the population Title VI (race, color, national origin) "
        "protects."
    ),
    "low-income-populations": (
        "People living below the federal poverty threshold, based on "
        "household income and family size (ACS Table S1701 / B17001)."
    ),
    "linguistically-isolated": (
        "Households where no member age 14+ speaks English “very "
        "well” — the Census Bureau's “limited English speaking "
        "household” measure (ACS Table B16002), formerly called "
        "“linguistically isolated.”"
    ),
    "people-with-disabilities": (
        "People reporting serious difficulty in at least one of six Census "
        "domains: hearing, vision, cognitive, ambulatory, self-care, or "
        "independent living (ACS disability questions). Protected under "
        "the ADA / Section 504, not Title VI."
    ),
    "older-adults": (
        "People age 65 and older, per standard Census Bureau age-bracket "
        "tables. Protected under the Age Discrimination Act of 1975, not "
        "Title VI."
    ),
    "youth-and-children": (
        "People under age 18, per standard Census Bureau age-bracket "
        "tables."
    ),
    "pregnant-people-and-new-parents": (
        "No Census measure captures current pregnancy. The closest proxy "
        "is the ACS fertility question — women age 15–50 who gave "
        "birth in the past 12 months (ACS Table B13002) — which only "
        "catches new parents, not pregnancy itself."
    ),
    "workers-in-affected-industries": (
        "People employed in a given industry sector, per Census "
        "industry-of-employment (NAICS) tables (ACS Table S2405). "
        "Describes an area's workforce mix, not any individual's "
        "employment status."
    ),
    "tribal-members-and-treaty-rights-holders": (
        "Enrolled members of federally recognized tribes and holders of "
        "treaty-reserved rights — a legal/political status set by tribal "
        "governments and treaties, not a Census variable. Self-identified "
        "American Indian / Alaska Native race (ACS Table B02001) is the "
        "closest, imperfect proxy."
    ),
    "populations-facing-environmental-harm": (
        "Not a single Census variable — identified by layering ACS "
        "demographics over environmental-exposure data (pollution "
        "sources, air toxics, hazardous sites), the approach used by "
        "EPA's now-discontinued EJScreen and Washington's Environmental "
        "Health Disparities Map."
    ),
    "overburdened-community-geography": (
        "A geographic area meeting Washington's HEAL Act definition of "
        "“overburdened community,” identified via the state's "
        "Environmental Health Disparities Map — combining ACS "
        "socioeconomic data, environmental exposure, and health outcomes "
        "by census tract."
    ),
}

# ── Facet 2b: Default constituency list (community-expandable) ────────────────
#
# Organized by relationship to a city system, not demographic attribute.
# Communities add or retire terms through the setup form; this list is the
# starting set they see when first configuring their profile.

DEFAULT_CONSTITUENCIES: dict[str, list[str]] = {
    "Mode": [
        "drivers",
        "transit-riders",
        "cyclists",
        "pedestrians",
        "wheelchair-and-mobility-device-users",
        "freight-and-delivery-operators",
    ],
    "Housing Tenure": [
        "renters",
        "homeowners",
        "landlords",
        "people-experiencing-homelessness",
        "mobile-home-and-manufactured-housing-residents",
    ],
    "Life Stage / Care": [
        "parents-of-young-children",
        "k12-families",
        "students",
        "older-adults",
        "caregivers",
    ],
    "Economic Role": [
        "small-business-owners",
        "gig-and-contract-workers",
        "employees-in-regulated-sectors",
        "license-and-permit-holders",
        "developers-and-builders",
        "nonprofit-service-providers",
    ],
    "Place": [
        "district-1",
        "district-2",
        "district-3",
        "district-4",
        "district-5",
        "district-6",
        "district-7",
    ],
    "Civic Role": [
        "community-council-members",
        "board-and-commission-appointees",
        "petitioners-and-appellants",
    ],
}

# Flat list of all default constituency terms for validation.
ALL_DEFAULT_CONSTITUENCIES: list[str] = [
    term for terms in DEFAULT_CONSTITUENCIES.values() for term in terms
]

# ── Facet 3: Stakes ───────────────────────────────────────────────────────────

RELATIONS = [
    "regulated",
    "served",
    "funded",
    "taxed",
    "sited-near",
    "employed-by",
    "represented-by",
]

RELATION_LABELS = {
    "regulated": "Regulated by this bill",
    "served": "Served by this bill",
    "funded": "Funded by this bill",
    "taxed": "Taxed by this bill",
    "sited-near": "Located near a facility sited by this bill",
    "employed-by": "Employed by an entity this bill affects",
    "represented-by": "Represented by a body this bill changes",
}

VALENCES = ["benefit", "burden", "mixed", "unclear"]

VALENCE_LABELS = {
    "benefit": "Benefit",
    "burden": "Burden",
    "mixed": "Mixed",
    "unclear": "Unclear",
}

DIRECTNESS_CHOICES = ["direct", "indirect", "procedural"]

DIRECTNESS_LABELS = {
    "direct": "Direct — bill names or governs this group",
    "indirect": "Indirect — bill changes conditions they operate in",
    "procedural": "Procedural — bill changes how they participate",
}

PARTICIPATION_WINDOWS = [
    "comment-open",
    "hearing-scheduled",
    "amendable",
    "closed",
    "already-enacted",
]

PARTICIPATION_WINDOW_LABELS = {
    "comment-open": "Comment Open",
    "hearing-scheduled": "Hearing Scheduled",
    "amendable": "In Committee (Amendable)",
    "closed": "Closed",
    "already-enacted": "Already Enacted",
}
