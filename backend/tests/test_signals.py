from __future__ import annotations

import pytest

from sponsor_radar.signals import dutch_required, is_tech_role, min_years, sponsorship_stance

DUTCH_REQUIRED = [
    "You are fluent in Dutch and English.",
    "Fluent in English and Dutch is a must.",
    "Native level proficiency in Dutch (essential)",
    "Excellent command of both Dutch and English, written and spoken;",
    "Strong written and verbal communication skills in Dutch (mandatory) and English",
    "Are fluent in both Dutch and English (minimum C1 level)",
    "We only have positions available for Dutch-speaking applicants residing in the Netherlands.",
    "Je spreekt en schrijft vloeiend Nederlands en Engels.",
    "Nederlands is essentieel voor het contact met klanten.",
]
NOT_REQUIRED = [
    "Dutch is a plus",
    "Speaks fluent English — Dutch is a bonus",
    "Nice to have is Dutch or French but not a requirement",
    "English is our daily working language; fluency in Dutch is not required.",
    "Fluency in English; proficiency in Dutch or willingness to learn.",
    "You communicate clearly in Dutch and/or English.",
    "Language: Dutch-speaking candidates preferred",
    "We offer Dutch language lessons to everyone who wants them.",
    "Floryn is a fast-growing Dutch fintech making business financing faster.",
    "Knowledge of Dutch tax law and reporting requirements.",
    "You will communicate with Dutch authorities and international partners.",
]


@pytest.mark.parametrize("text", DUTCH_REQUIRED)
def test_dutch_required(text):
    assert dutch_required(f"About the role\nWe build payment software for merchants across Europe.\n{text}")


@pytest.mark.parametrize("text", NOT_REQUIRED)
def test_dutch_not_required(text):
    assert not dutch_required(f"About the role\nWe build payment software for merchants across Europe.\n{text}")


def test_mostly_dutch_description_requires_dutch():
    description = (
        "Bij ons team werk je aan de software van onze klanten. Je bent verantwoordelijk voor het ontwerpen en bouwen "
        "van een nieuwe applicatie voor de zorg. Wij zoeken een collega met een goede kennis van Java en een passie "
        "voor het vak. Ook denk je mee over de architectuur van het platform en werk je samen met de product owner. "
        "Wat bieden wij? Een goed salaris, een laptop en de ruimte om te groeien in jouw rol bij een van de mooiste "
        "bedrijven van het land."
    )
    assert dutch_required(description, "Java Developer")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3+ years of experience with Python", 3),
        ("At least 2 years of professional experience in backend development", 2),
        ("2-4 years of experience in data engineering", 2),
        ("0–3 years of experience (graduates welcome)", 0),
        ("Minimum of 5 years in a similar role", 5),
        ("Je hebt minimaal 3 jaar ervaring als software engineer", 3),
        ("Minimaal drie jaar ervaring als Security Engineer", 3),
        ("5+ years of experience in software engineering, including 2+ years with Go", 2),
        ("Ben je minimaal 18 jaar oud", None),
        ("For more than 30 years, we have been developing solutions", None),
        ("We have been around for 7 years and grow every year", None),
        ("Experience with Kubernetes is a plus", None),
    ],
)
def test_min_years(text, expected):
    assert min_years(text) == expected


# Sponsorship stance. Sentences marked SP (Schuberg Philis) and Sytac are copied from their live postings.
STANCE = [
    # refuses_visa
    ("Currently we do not offer visa sponsorship.", "refuses_visa"),  # SP
    ("We bieden geen relocatie of visumsponsoring en nemen geen sollicitaties vanuit het buitenland in behandeling.",
     "refuses_visa"),  # SP
    ("No sponsorship is available, and candidates must already reside in the Netherlands.", "refuses_visa"),  # Sytac
    ("Fluent in English + EU residency (no sponsorship).", "refuses_visa"),  # Sytac
    ("Unfortunately we are unable to sponsor a work permit for this role.", "refuses_visa"),
    ("You must already have the right to work in the Netherlands.", "refuses_visa"),
    ("Valid EU work permit required.", "refuses_visa"),
    ("Een geldige werkvergunning is vereist; werkvergunning vereist voor deze rol.", "refuses_visa"),
    ("Please note: we don’t offer visa sponsorship.", "refuses_visa"),
    # offers
    ("For this role we offer relocation support and more information about our perks can be found on our What we "
     "offer page.", "offers"),  # SP
    ("Visa sponsorship available for eligible candidates.", "offers"),
    ("We can sponsor your visa as a recognised kennismigrant sponsor.", "offers"),
    ("We provide a relocation package and full visa sponsorship for international hires.", "offers"),
    # refuses_relocation
    ("We do not provide relocation sponsorship.", "refuses_relocation"),  # SP
    ("At this moment we are not providing relocation sponsorships.", "refuses_relocation"),  # SP
    ("Please note: At this point we are only considering applications from candidates currently based in the "
     "Netherlands.", "refuses_relocation"),  # SP
    ("NL residency required, expats already living and working in the Netherlands are very welcome.",
     "refuses_relocation"),  # Sytac
    ("Please note: we don’t offer relocation support for this role.", "refuses_relocation"),
    ("You must be based in the Netherlands.", "refuses_relocation"),
    # silent: the phrases appear but state no stance
    ("Whether or not you need visa sponsorship, we would love to hear from you.", "silent"),
    ("IMC is unable to obtain immigration sponsorship for candidates who currently have citizenship from Russia.",
     "silent"),
    ("You are based in the Netherlands, have an EU passport, or have a partner / highly skilled migrant visa here.",
     "refuses_relocation"),
    ("You are preferably already living in the Netherlands.", "silent"),
    ("Based in Amsterdam, or willing to relocate.", "silent"),
    ("Company-sponsored sports teams and a relocation of our office to Utrecht.", "silent"),
    ("Experience integrating card networks such as Visa and Mastercard.", "silent"),
    ("We work with highly skilled engineers on our platform.", "silent"),
]


@pytest.mark.parametrize(("text", "stance"), STANCE)
def test_sponsorship_stance(text, stance):
    assert sponsorship_stance(f"About the role\nWe build payment software for merchants.\n{text}") == stance


def test_stance_precedence():
    offer = "We offer a relocation package."
    assert sponsorship_stance(f"{offer}\nWe do not offer visa sponsorship.") == "refuses_visa"
    assert sponsorship_stance(f"{offer}\nYou must be based in the Netherlands.") == "offers"
    # A negation in another sentence does not void an offer.
    assert sponsorship_stance(f"No recruiters please.\n{offer}") == "offers"


# Technical support and pre-sales titles count as tech roles; titles taken from live postings.
TECH_TITLES = [
    ("Technical Support Specialist - Payments", True),
    ("Support Engineer", True),
    ("Solutions Engineer", True),
    ("Sales Engineer", True),
    ("Forward Deployed Architect - Amsterdam", True),
    ("Pre-Sales Consultant - AV / UC", True),
    ("Solutions Architect - Netherlands", True),
    ("Junior IT Support Specialist", True),
    ("Second Line Support Agent (f/m/x)", True),
    ("Systeembeheerder", True),
    ("Technisch Applicatiebeheerder Bancaire Applicaties", True),
    ("Technisch Helpdesk Medewerker", True),
    ("Customer Support Agent", False),
    ("Sales Support Specialist", False),
    ("Backoffice Support Specialist", False),
]


@pytest.mark.parametrize(("title", "tech"), TECH_TITLES)
def test_tech_support_and_presales_titles(title, tech):
    assert is_tech_role(title) is tech
