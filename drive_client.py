from typing import Dict
"""
drive_client.py
Client Google Sheets pour l'écriture et le formatage des tickets classifiés.

Aucune valeur n'est codée en dur : catégories, urgences et couleurs sont
entièrement dérivées du profil actif passé au constructeur.
"""

import os
import time

import gspread
from gspread_formatting import (
    batch_updater,
    CellFormat,
    Color,
    TextFormat,
    set_column_width,
)
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Palette de couleurs pour les niveaux d'urgence (du plus critique au plus anodin).
# Adaptée dynamiquement au nombre d'urgences déclarées dans le profil.
_URGENCY_PALETTE = [
    Color(0.96, 0.26, 0.21),   # Rouge       – niveau 1 (le plus urgent)
    Color(1.00, 0.60, 0.00),   # Orange
    Color(1.00, 0.90, 0.20),   # Jaune
    Color(0.42, 0.78, 0.42),   # Vert
    Color(0.53, 0.81, 0.98),   # Bleu clair  – niveau 5
    Color(0.75, 0.60, 0.90),   # Violet clair
    Color(0.80, 0.80, 0.80),   # Gris        – débordement si > 6 niveaux
]

HEADER_BG_COLOR   = Color(0.20, 0.40, 0.75)
HEADER_TEXT_COLOR = Color(1, 1, 1)


class DriveClient:
    """
    Écrit les tickets classifiés dans un Google Sheet structuré selon le profil actif.

    Paramètres
    ----------
    sheet_id : str
        Identifiant du Google Sheet cible.
    profile : dict
        Profil chargé via profile_manager.load_profile().
        Doit contenir les clés "categories" et "urgences".
    """

    def __init__(self, sheet_id: str, profile: dict):
        self.sheet_id = sheet_id
        self.profile  = profile

        # Dérivé du profil — aucune constante globale
        self.categories    = [c["id"]    for c in profile.get("categories", [])]
        self.urgency_order = {u["label"]: i for i, u in enumerate(profile.get("urgences", []))}
        self.urgency_colors = self._build_urgency_colors()

        creds        = Credentials.from_authorized_user_file("token.json", SCOPES)
        self.client  = gspread.authorize(creds)
        self.sheet   = self.client.open_by_key(self.sheet_id)
        self._ensure_sheets_exist()

    # ── Couleurs ──────────────────────────────────────────────────────────────

    def _build_urgency_colors(self) -> Dict[str, Color]:
        """
        Associe chaque label d'urgence à une couleur de la palette.
        Si le profil déclare plus d'urgences que la palette, la dernière couleur
        (gris) est réutilisée pour les niveaux supplémentaires.
        """
        urgences = self.profile.get("urgences", [])
        colors: Dict[str, Color] = {}
        for i, urg in enumerate(urgences):
            colors[urg["label"]] = _URGENCY_PALETTE[min(i, len(_URGENCY_PALETTE) - 1)]
        return colors

    # ── Initialisation des feuilles ───────────────────────────────────────────

    def _ensure_sheets_exist(self) -> None:
        """Crée les feuilles manquantes et vérifie les en-têtes."""
        existing = [ws.title for ws in self.sheet.worksheets()]
        for cat_id in self.categories:
            if cat_id not in existing:
                ws = self.sheet.add_worksheet(title=cat_id, rows="1000", cols="3")
                ws.append_row(["Sujet", "Urgence", "Synthèse"])
                print(f"Feuille '{cat_id}' créée")
            else:
                ws = self.sheet.worksheet(cat_id)
                if ws.row_values(1) != ["Sujet", "Urgence", "Synthèse"]:
                    ws.insert_row(["Sujet", "Urgence", "Synthèse"], 1)

    # ── Écriture ──────────────────────────────────────────────────────────────

    def write_to_sheet(
        self,
        categorie: str,
        sujet: str,
        urgence: str,
        synthese: str,
    ) -> None:
        """
        Ajoute une ligne dans la feuille correspondant à la catégorie.
        Crée la feuille à la volée si elle n'existe pas encore.
        """
        try:
            worksheet = self.sheet.worksheet(categorie)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self.sheet.add_worksheet(title=categorie, rows="1000", cols="3")
            worksheet.append_row(["Sujet", "Urgence", "Synthèse"])
        worksheet.append_row([sujet, urgence, synthese])
        print(f" Ajouté dans '{categorie}' : {sujet[:50]}")

    # ── Finalisation ──────────────────────────────────────────────────────────

    def finalize_all_sheets(self) -> None:
        """Trie et formate toutes les feuilles du profil actif."""
        print("\n Finalisation des feuilles Google Sheet")
        for cat_id in self.categories:
            try:
                ws = self.sheet.worksheet(cat_id)
                print(f"  → Tri de '{cat_id}'")
                self._sort_sheet(ws)
                time.sleep(2)
                print(f"  → Formatage de '{cat_id}'")
                self._format_sheet(ws)
                time.sleep(3)
                print(f"'{cat_id}' trié et formaté.")
            except gspread.exceptions.WorksheetNotFound:
                print(f" Feuille '{cat_id}' introuvable, ignorée")
        print("Formatage terminé")

    # ── Tri ───────────────────────────────────────────────────────────────────

    def _sort_sheet(self, worksheet: gspread.Worksheet) -> None:
        """Trie les lignes par niveau d'urgence (ordre déclaré dans le profil)."""
        all_rows = worksheet.get_all_values()
        if len(all_rows) <= 1:
            return
        header = all_rows[0]
        data   = sorted(
            all_rows[1:],
            key=lambda row: self.urgency_order.get(row[1], 99),
        )
        worksheet.clear()
        time.sleep(1)
        worksheet.append_row(header)
        if data:
            worksheet.append_rows(data)

    # ── Formatage ─────────────────────────────────────────────────────────────

    def _format_sheet(self, worksheet: gspread.Worksheet) -> None:
        """Applique les couleurs d'en-tête et d'urgence en un seul batch."""
        all_rows = worksheet.get_all_values()
        if len(all_rows) <= 1:
            return

        with batch_updater(worksheet.spreadsheet) as batch:
            # En-tête
            batch.format_cell_range(
                worksheet,
                "A1:C1",
                CellFormat(
                    backgroundColor=HEADER_BG_COLOR,
                    textFormat=TextFormat(
                        bold=True,
                        foregroundColor=HEADER_TEXT_COLOR,
                        fontSize=11,
                    ),
                ),
            )
            # Couleur par urgence (colonne B)
            for i, row in enumerate(all_rows[1:], start=2):
                label = row[1] if len(row) > 1 else ""
                color = self.urgency_colors.get(label)
                if color:
                    batch.format_cell_range(
                        worksheet,
                        f"B{i}",
                        CellFormat(
                            backgroundColor=color,
                            textFormat=TextFormat(bold=True),
                        ),
                    )

        # Largeurs de colonnes (hors batch)
        time.sleep(1)
        set_column_width(worksheet, "A", 300)
        time.sleep(0.5)
        set_column_width(worksheet, "B", 120)
        time.sleep(0.5)
        set_column_width(worksheet, "C", 500)
