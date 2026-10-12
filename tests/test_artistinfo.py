"""Ce que MusicBrainz et Wikipédia disent d'un artiste : lecture de la fiche, résumé, présentation, et ce qu'on en garde d'un passage à l'autre.

Aucun appel réseau : le client est remplacé par un double qui rejoue des réponses préparées.
"""

import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.music import artistinfo
from libraries.music.musicbrainz import MusicBrainzError

MBID = "056e4f3e-765f-4e34-b4ce-4c2d3ce6f1d6"
THOMAS = "0e6a5d0a-1f2b-4c3d-8e4f-5a6b7c8d9e01"
GUY = "1f7b6e1b-2a3c-4d4e-9f50-6b7c8d9e0f12"
WIKIDATA = "https://www.wikidata.org/wiki/Special:EntityData/Q185.json"
FR = "https://fr.wikipedia.org/api/rest_v1/page/summary/Daft_Punk"
EN = "https://en.wikipedia.org/api/rest_v1/page/summary/Daft_Punk"


def url(kind, resource):
    return {"type": kind, "url": {"resource": resource}}


def membre(mbid, nom, begin=None, end=None, ended=False, roles=(), direction="backward"):
    return {"type": "member of band", "direction": direction, "begin": begin, "end": end, "ended": ended,
            "attributes": list(roles), "artist": {"id": mbid, "name": nom}}


def groupe(**kw):
    data = {"id": MBID, "name": "Daft Punk", "type": "Group", "area": {"name": "France"},
            "life-span": {"begin": "1993-01", "end": None, "ended": False}, "disambiguation": "French electronic duo",
            "relations": [url("official homepage", "https://www.daftpunk.com/"), url("wikidata", "https://www.wikidata.org/wiki/Q185"),
                          membre(THOMAS, "Thomas Bangalter", "1993", roles=["synthesizer"]), membre(GUY, "Guy-Manuel de Homem-Christo", "1993", "2021", True)]}
    data.update(kw)
    return data


def resume(texte="Daft Punk est un duo français.", **kw):
    data = {"type": "standard", "title": "Daft Punk", "extract": texte, "content_urls": {"desktop": {"page": "https://fr.wikipedia.org/wiki/Daft_Punk"}}}
    data.update(kw)
    return data


class ClientFactice:
    """Remplace MusicBrainz : rejoue des réponses par adresse, et garde la trace des appels."""

    def __init__(self, reponses):
        self.reponses = reponses
        self.appels = []

    def _repondre(self, cle):
        self.appels.append(cle)
        reponse = self.reponses.get(cle)
        if reponse is None:
            raise MusicBrainzError("introuvable (HTTP 404)", 404)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    def artist(self, mbid):
        return self._repondre(f"artist/{mbid}")

    def external(self, adresse):
        return self._repondre(adresse)


class TestFiche(unittest.TestCase):
    def test_type_pays_et_dates(self):
        info = artistinfo.parse(groupe())
        self.assertEqual((info["type"], info["area"], info["begin"], info["end"], info["ended"]), ("Group", "France", "1993", "", False))
        self.assertEqual(info["disambiguation"], "French electronic duo")

    def test_fiche_vide(self):
        info = artistinfo.parse({})
        self.assertEqual((info["type"], info["area"], info["members"], info["links"], info["wiki"]), ("", "", [], [], None))
        self.assertEqual(artistinfo.facts(info), "")

    def test_membres_actuels_avant_les_anciens(self):
        noms = [m["name"] for m in artistinfo.parse(groupe())["members"]]
        self.assertEqual(noms, ["Thomas Bangalter", "Guy-Manuel de Homem-Christo"])

    def test_membre_et_ses_roles(self):
        membre_ = artistinfo.parse(groupe())["members"][0]
        self.assertEqual((membre_["mbid"], membre_["begin"], membre_["roles"]), (THOMAS, "1993", ["synthesizer"]))

    def test_membre_d_origine_n_est_pas_un_instrument(self):
        unique, = artistinfo.parse(groupe(relations=[membre(THOMAS, "T", "1993", roles=["original", "bass"])]))["members"]
        self.assertEqual(unique["roles"], ["bass"])

    def test_un_membre_revenu_n_a_qu_une_ligne(self):
        data = groupe(relations=[membre(THOMAS, "T", "1990", "1995", True, ["guitar"]), membre(THOMAS, "T", "1998", None, False, ["vocals", "guitar"])])
        unique, = artistinfo.parse(data)["members"]
        self.assertEqual((unique["begin"], unique["end"], unique["ended"], unique["roles"]), ("1990", "", False, ["guitar", "vocals"]))

    def test_les_groupes_dont_il_est_membre_ne_sont_pas_ses_membres(self):
        data = groupe(type="Person", relations=[membre(THOMAS, "Un groupe", "1990", direction="forward")])
        self.assertEqual(artistinfo.parse(data)["members"], [])
        self.assertEqual(artistinfo.parse(groupe(relations=[membre(THOMAS, "Un groupe", direction="forward")]))["members"], [])

    def test_un_artiste_solo_n_a_pas_de_membres(self):
        self.assertEqual(artistinfo.parse(groupe(type="Person"))["members"], [])

    def test_membres_plafonnes(self):
        data = groupe(type="Orchestra", relations=[membre(f"{n:08x}-0000-0000-0000-000000000000", f"M{n:03d}") for n in range(artistinfo.MAX_MEMBERS + 20)])
        self.assertEqual(len(artistinfo.parse(data)["members"]), artistinfo.MAX_MEMBERS)


class TestLiens(unittest.TestCase):
    def liens(self, *rels):
        return artistinfo.links({"relations": list(rels)})

    def test_site_officiel_d_abord_et_noms_lisibles(self):
        found = self.liens(url("social network", "https://www.instagram.com/daftpunk/"), url("official homepage", "https://www.daftpunk.com/"),
                           url("bandcamp", "https://daftpunk.bandcamp.com/"))
        self.assertEqual([(f["label"], f["url"]) for f in found], [("Site officiel", "https://www.daftpunk.com/"), ("Bandcamp", "https://daftpunk.bandcamp.com/"),
                                                                    ("Instagram", "https://www.instagram.com/daftpunk/")])

    def test_bases_de_donnees_et_boutiques_ecartees(self):
        self.assertEqual(self.liens(url("discogs", "https://www.discogs.com/artist/1"), url("purchase for download", "https://shop.example/x")), [])

    def test_seuls_les_liens_web_sont_gardes(self):
        self.assertEqual(self.liens(url("official homepage", "javascript:alert(1)"), url("official homepage", "ftp://x.example/"), url("official homepage", "")), [])

    def test_pas_de_doublon(self):
        self.assertEqual(len(self.liens(url("official homepage", "https://a.example/"), url("official homepage", "https://a.example/"))), 1)

    def test_domaine_inconnu_donne_son_nom(self):
        found, = self.liens(url("social network", "https://www.exemple.org/profil"))
        self.assertEqual(found["label"], "exemple.org")

    def test_liens_plafonnes(self):
        found = self.liens(*[url("social network", f"https://site{n}.example/") for n in range(20)])
        self.assertEqual(len(found), artistinfo.MAX_LINKS)


class TestPresentation(unittest.TestCase):
    def test_vies(self):
        for info, attendu in (({"begin": "1993", "end": "2021"}, "1993 – 2021"), ({"begin": "1993"}, "depuis 1993"), ({"begin": "1970", "type": "Person"}, "né en 1970"),
                              ({"begin": "1950", "ended": True}, "1950 – ?"), ({"end": "2001"}, "jusqu'en 2001"), ({}, "")):
            with self.subTest(info=info):
                self.assertEqual(artistinfo.lifespan(info), attendu)

    def test_faits(self):
        self.assertEqual(artistinfo.facts(artistinfo.parse(groupe())), "Groupe · France · depuis 1993")
        self.assertEqual(artistinfo.facts({"type": "Person", "begin": "1970"}), "Artiste solo · né en 1970")

    def test_periode_d_un_membre(self):
        for membre_, attendu in (({"begin": "1993", "end": "2001"}, "1993 – 2001"), ({"begin": "1993", "end": "1993"}, "1993"), ({"begin": "1993"}, "depuis 1993"),
                                 ({"begin": "1993", "ended": True}, "1993 – ?"), ({}, "")):
            with self.subTest(membre=membre_):
                self.assertEqual(artistinfo.period(membre_), attendu)

    def test_resume_coupe_a_la_fin_d_une_phrase(self):
        texte = "Une phrase assez longue. " * 60
        court = artistinfo.shorten(texte, 200)
        self.assertLessEqual(len(court), 200)
        self.assertTrue(court.endswith("."))

    def test_resume_sans_phrase_coupe_avec_des_points(self):
        self.assertTrue(artistinfo.shorten("mot " * 500, 100).endswith("…"))

    def test_resume_court_inchange_et_espaces_resserres(self):
        self.assertEqual(artistinfo.shorten("Un   duo\n français."), "Un duo français.")


class TestWikipedia(unittest.TestCase):
    def fetch(self, reponses, data=None):
        client = ClientFactice({f"artist/{MBID}": data or groupe(), **reponses})
        return artistinfo.fetch(client, MBID), client

    def test_resume_en_francais(self):
        info, _ = self.fetch({WIKIDATA: {"entities": {"Q185": {"sitelinks": {"frwiki": {"title": "Daft Punk"}, "enwiki": {"title": "Daft Punk"}}}}}, FR: resume()})
        self.assertEqual(info["wiki"], {"lang": "fr", "title": "Daft Punk", "url": "https://fr.wikipedia.org/wiki/Daft_Punk", "extract": "Daft Punk est un duo français."})

    def test_a_defaut_l_anglais(self):
        info, client = self.fetch({WIKIDATA: {"entities": {"Q185": {"sitelinks": {"enwiki": {"title": "Daft Punk"}}}}}, EN: resume("A French duo.", content_urls={})})
        self.assertEqual((info["wiki"]["lang"], info["wiki"]["extract"], info["wiki"]["url"]), ("en", "A French duo.", "https://en.wikipedia.org/wiki/Daft_Punk"))
        self.assertNotIn(FR, client.appels)

    def test_article_francais_introuvable_repli_sur_l_anglais(self):
        info, _ = self.fetch({WIKIDATA: {"entities": {"Q185": {"sitelinks": {"frwiki": {"title": "Daft Punk"}, "enwiki": {"title": "Daft Punk"}}}}}, EN: resume("A French duo.")})
        self.assertEqual(info["wiki"]["lang"], "en")

    def test_page_d_homonymes_ecartee(self):
        info, _ = self.fetch({WIKIDATA: {"entities": {"Q185": {"sitelinks": {"frwiki": {"title": "Daft Punk"}}}}}, FR: resume(type="disambiguation")})
        self.assertIsNone(info["wiki"])

    def test_sans_article(self):
        info, _ = self.fetch({WIKIDATA: {"entities": {"Q185": {"sitelinks": {}}}}})
        self.assertIsNone(info["wiki"])
        self.assertEqual(info["type"], "Group")

    def test_sans_relation_wikipedia_aucune_requete_de_plus(self):
        info, client = self.fetch({}, groupe(relations=[]))
        self.assertEqual((info["wiki"], client.appels), (None, [f"artist/{MBID}"]))

    def test_article_designe_directement(self):
        data = groupe(relations=[url("wikipedia", "https://en.wikipedia.org/wiki/Daft_Punk")])
        info, _ = self.fetch({EN: resume("A French duo.")}, data)
        self.assertEqual(info["wiki"]["lang"], "en")

    def test_titre_accentue_encode(self):
        data = groupe(relations=[url("wikidata", "https://www.wikidata.org/wiki/Q9")])
        reponses = {"https://www.wikidata.org/wiki/Special:EntityData/Q9.json": {"entities": {"Q9": {"sitelinks": {"frwiki": {"title": "Étienne Daho"}}}}},
                    "https://fr.wikipedia.org/api/rest_v1/page/summary/%C3%89tienne_Daho": resume("Un chanteur.")}
        info, _ = self.fetch(reponses, data)
        self.assertEqual(info["wiki"]["extract"], "Un chanteur.")

    def test_panne_du_reseau_remontee(self):
        with self.assertRaises(MusicBrainzError) as plante:
            self.fetch({WIKIDATA: MusicBrainzError("coupure")})
        self.assertIsNone(plante.exception.code)

    def test_artiste_introuvable_remonte_en_404(self):
        client = ClientFactice({})
        with self.assertRaises(MusicBrainzError) as plante:
            artistinfo.fetch(client, MBID)
        self.assertEqual(plante.exception.code, 404)

    def test_adresse_wikipedia_dangereuse_remplacee(self):
        info, _ = self.fetch({WIKIDATA: {"entities": {"Q185": {"sitelinks": {"frwiki": {"title": "Daft Punk"}}}}},
                              FR: resume(content_urls={"desktop": {"page": "javascript:alert(1)"}})})
        self.assertEqual(info["wiki"]["url"], "https://fr.wikipedia.org/wiki/Daft_Punk")


class TestMemoire(unittest.TestCase):
    def test_aller_retour(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "artists.json"
            entrees = {MBID: {"fetched": "2026-10-01", "info": artistinfo.parse(groupe())}}
            chemin.write_text(artistinfo.dump(entrees), encoding="utf-8")
            self.assertEqual(artistinfo.load(chemin), entrees)

    def test_absent_corrompu_ou_d_une_autre_version(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "artists.json"
            self.assertEqual(artistinfo.load(chemin), {})
            chemin.write_text("{", encoding="utf-8")
            self.assertEqual(artistinfo.load(chemin), {})
            chemin.write_text('{"version": 0, "artists": {"x": {"info": {}}}}', encoding="utf-8")
            self.assertEqual(artistinfo.load(chemin), {})

    def test_entrees_abimees_ignorees(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "artists.json"
            chemin.write_text('{"version": 1, "artists": {"a": 3, "b": {"info": 4}, "c": {"info": {}}}}', encoding="utf-8")
            self.assertEqual(list(artistinfo.load(chemin)), ["c"])

    def test_peremption(self):
        aujourdhui = date(2026, 10, 12)
        recent = {"fetched": (aujourdhui - timedelta(days=artistinfo.STALE_DAYS)).isoformat()}
        vieux = {"fetched": (aujourdhui - timedelta(days=artistinfo.STALE_DAYS + 1)).isoformat()}
        self.assertFalse(artistinfo.stale(recent, aujourdhui))
        self.assertTrue(artistinfo.stale(vieux, aujourdhui))

    def test_date_illisible_perimee(self):
        for entree in ({}, {"fetched": "hier"}, {"fetched": 5}):
            with self.subTest(entree=entree):
                self.assertTrue(artistinfo.stale(entree))


if __name__ == "__main__":
    unittest.main()
