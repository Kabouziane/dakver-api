"""
Client VIES (VAT Information Exchange System) — Commission Européenne.
API officielle, gratuite, sans clé API requise.

Documentation : https://ec.europa.eu/taxation_customs/vies/#/technical-information
"""
import logging
import re

import requests

logger = logging.getLogger(__name__)

VIES_URL = 'https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{country}/vat/{number}'
TIMEOUT  = 5  # secondes


def normalize_vat(raw: str) -> tuple[str, str] | None:
    """
    Normalise un numéro de TVA et retourne (country_code, number).
    Accepte : "BE 0123.456.789", "BE0123456789", "0123456789" (assume BE).
    Retourne None si le format est irrémédiablement invalide.
    """
    cleaned = re.sub(r'[\s.\-]', '', raw.strip().upper())

    # Numéro sans pays → on assume Belgique
    if re.match(r'^\d{8,12}$', cleaned):
        cleaned = 'BE' + cleaned

    m = re.match(r'^([A-Z]{2})(\d{5,12})$', cleaned)
    return (m.group(1), m.group(2)) if m else None


class ViesResult:
    def __init__(self, valid: bool, name: str | None = None,
                 address: str | None = None, error: str | None = None,
                 unavailable: bool = False):
        self.valid       = valid
        self.name        = name if name and name != '---' else None
        self.address     = address if address and address != '---' else None
        self.error       = error
        self.unavailable = unavailable  # True = VIES est down, pas une erreur de format


def check_vat(raw: str) -> ViesResult:
    """
    Valide un numéro de TVA via VIES.

    Cas de retour :
      .valid=True              → TVA active, .name et .address disponibles si partagés
      .valid=False, .error     → TVA invalide ou inconnue
      .unavailable=True        → VIES inaccessible (timeout/panne) — ne pas bloquer l'utilisateur
    """
    parsed = normalize_vat(raw)
    if not parsed:
        return ViesResult(valid=False, error='Format de TVA invalide (ex: BE 0123.456.789).')

    country, number = parsed
    url = VIES_URL.format(country=country, number=number)

    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={'Accept': 'application/json'})
    except requests.Timeout:
        logger.warning('VIES timeout pour %s%s', country, number)
        return ViesResult(valid=False, unavailable=True,
                          error='Service VIES indisponible (timeout). La vérification sera effectuée ultérieurement.')
    except requests.RequestException as e:
        logger.error('VIES erreur réseau : %s', e)
        return ViesResult(valid=False, unavailable=True,
                          error='Service VIES inaccessible. Réessayez dans quelques instants.')

    # VIES retourne 400 si le format ne correspond pas à ses propres règles
    if resp.status_code == 400:
        return ViesResult(valid=False, error='Numéro TVA invalide selon VIES.')

    if resp.status_code != 200:
        logger.warning('VIES réponse inattendue %s pour %s%s', resp.status_code, country, number)
        return ViesResult(valid=False, unavailable=True, error='Service VIES indisponible.')

    data = resp.json()
    if not data.get('valid'):
        return ViesResult(valid=False, error='Numéro TVA non reconnu ou inactif dans VIES.')

    return ViesResult(
        valid=True,
        name=data.get('name'),
        address=data.get('address'),
    )
