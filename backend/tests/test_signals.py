from __future__ import annotations

import pytest

from sponsor_radar.signals import dutch_required, min_years

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
