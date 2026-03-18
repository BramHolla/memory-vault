# Memory Vault — Commando's

## Nieuwe herinneringen toevoegen (jouw eigen sync)

```powershell
.venv\Scripts\python.exe sync.py --api-key sk_YOUR_API_KEY_HERE "C:\pad\naar\mydata~*.zip"
```

Doet automatisch: ZIP verwerken → user_id instellen → media uploaden naar R2 → database uploaden.
App toont nieuwe content binnen ~5 minuten.

---

## Fly.io — App beheer (`memoryvault`)

### Status bekijken
```powershell
fly status -a memoryvault
```

### Logs bekijken (live)
```powershell
fly logs -a memoryvault
```

### App herstarten
```powershell
fly apps restart memoryvault
```

### Nieuwe versie deployen (na code wijzigingen)
```powershell
fly deploy
```

### Secrets bekijken (namen, niet waarden)
```powershell
fly secrets list -a memoryvault
```

### Secret updaten
```powershell
fly secrets set GMAIL_APP_PASSWORD="nieuwe_waarde" -a memoryvault
```

### App openen in browser
```powershell
fly apps open -a memoryvault
```
Of ga direct naar: https://memoryvault.fly.dev

---

## Admin-panel

Beheer gebruikers via: **https://memoryvault.fly.dev/admin**

- Gebruiker toevoegen → uitnodigingsmail wordt automatisch verstuurd
- Reset wachtwoord → reset-mail naar de gebruiker
- API-key kopiëren → doorgeven voor sync

---

## sync.exe bouwen (voor vrienden)

```powershell
.venv\Scripts\pip.exe install pyinstaller
.venv\Scripts\pyinstaller.exe --onefile sync.py --name sync
```

Uitvoer staat in `dist\sync.exe`. Herbouwen is alleen nodig als `sync.py`, `config.py`, `users_db.py` of `downloader.py` verandert.

**Instructies voor vriend:**
```
sync.exe --api-key sk_HUNKEY pad\naar\mydata~*.zip
```

---

## Lokaal draaien (voor testen)

```powershell
.venv\Scripts\python.exe app.py
```
Ga naar: http://localhost:5000

---

## Eenmalig: foto's verplaatsen (al gedaan)

```powershell
# Controleer zonder verwijderen
.venv\Scripts\python.exe fix_move_media.py --user-id bramh

# Verwijder originelen na verificatie
.venv\Scripts\python.exe fix_move_media.py --user-id bramh --delete
```

---

## R2-structuur

```
snapchat-memories (bucket)
  users.db                          ← gebruikersdatabase
  users/
    bramh/
      memories.db                   ← jouw herinneringen-database
      media/                        ← jouw foto's en video's
    annev/
      memories.db
      media/
```