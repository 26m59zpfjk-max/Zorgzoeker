"""Recall op de evaluatieset. Verwachte ids komen uit tests/evaluatie.yaml, niet uit de zoekmachine."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from zorgzoeker.laden import laad_document
from zorgzoeker.zoeken import Index

DREMPEL = 0.8
_AANHALING = re.compile(r'"([^"]+)"')
_DOELGROEP = re.compile(r"doelgroep \(([^)]+)\)")
_PRODUCT = re.compile(r"productcode [^(]+\(([^)]+)\)")


def _vragen() -> list[dict]:
    return yaml.safe_load((Path(__file__).parent / "evaluatie.yaml").read_text(encoding="utf-8"))


def _dataset() -> dict:
    pad = Path(__file__).resolve().parents[1] / "data" / "aanbieders.json"
    return laad_document(pad)


def _waarden(veld) -> list[str]:
    if not isinstance(veld, dict):
        return []
    waarde = veld.get("waarde")
    if isinstance(waarde, list):
        return [str(item) for item in waarde if not isinstance(item, dict)]
    if isinstance(waarde, str):
        return [waarde]
    return []


def _corpus(aanbieder: dict) -> str:
    stukken = [str(aanbieder.get("naam") or "")]
    for sleutel in ("expertise", "doelgroepen", "type_aanbod", "werkgebied"):
        stukken.extend(_waarden(aanbieder.get(sleutel)))
    for product in (aanbieder.get("productcodes") or {}).get("waarde") or []:
        if isinstance(product, dict):
            stukken.append(str(product.get("code") or ""))
            stukken.append(str(product.get("omschrijving") or ""))
    for vestiging in (aanbieder.get("vestigingen") or {}).get("waarde") or []:
        if isinstance(vestiging, dict):
            stukken.extend(_waarden(vestiging.get("plaats")))
            stukken.append(str(vestiging.get("plaats") or ""))
    return "\n".join(stukken)


def test_minstens_vijftig_evaluatievragen() -> None:
    assert len(_vragen()) >= 50


def test_recall_evaluatie() -> None:
    index = Index(_dataset())
    fouten: list[str] = []
    for item in _vragen():
        treffers = index.zoek(item["vraag"])
        if item.get("breder"):
            if not treffers or not all(
                treffer.breder and "Breder resultaat" in treffer.reden and "bovencategorie" in treffer.reden
                for treffer in treffers
            ):
                fouten.append(f"{item['id']} breder-label ontbreekt ({item['vraag']})")
                continue
            for label in item.get("boven_label") or []:
                if label.lower() not in treffers[0].reden.lower():
                    fouten.append(f"{item['id']} mist bovencategorie {label}")
            if "geen treffer op" not in treffers[0].reden:
                fouten.append(f"{item['id']} noemt het kindbegrip niet als gemist")
            continue
        verwacht = [regel["id"] for regel in item.get("verwacht") or []]
        if not verwacht:
            fouten.append(f"{item['id']} precieze vraag zonder verwachte aanbieders")
            continue
        k = 10 if len(verwacht) <= 10 else 20
        ids = [treffer.id for treffer in treffers[:k]]
        geraakt = sum(1 for aanbieder_id in verwacht if aanbieder_id in ids)
        recall = geraakt / len(verwacht)
        if recall < DREMPEL:
            mist = [aanbieder_id for aanbieder_id in verwacht if aanbieder_id not in ids]
            fouten.append(
                f"{item['id']} recall@{k}={recall:.2f} ({geraakt}/{len(verwacht)}) "
                f"{item['vraag']!r} mist {mist[:6]}"
            )
    assert not fouten, "\n".join(fouten)


def test_redenen_citeren_echte_velden() -> None:
    document = _dataset()
    index = Index(document)
    per_id = {aanbieder["id"]: aanbieder for aanbieder in document["aanbieders"]}
    fouten: list[str] = []
    for item in _vragen():
        for treffer in index.zoek(item["vraag"]):
            bron = _corpus(per_id[treffer.id])
            laag = bron.lower()
            reden = treffer.reden
            if "wachttijd" in reden.lower():
                fouten.append(f"{item['id']} {treffer.id} noemt wachttijd")
            for citaat in _AANHALING.findall(reden):
                if citaat not in bron:
                    fouten.append(f"{item['id']} {treffer.id} citaat ontbreekt: {citaat[:80]}")
            for citaat in _DOELGROEP.findall(reden):
                if citaat.lower() not in laag:
                    fouten.append(f"{item['id']} {treffer.id} doelgroep-citaat ontbreekt: {citaat[:80]}")
            for citaat in _PRODUCT.findall(reden):
                if citaat not in bron:
                    fouten.append(f"{item['id']} {treffer.id} product-citaat ontbreekt: {citaat[:80]}")
    assert not fouten, "\n".join(fouten[:30])
