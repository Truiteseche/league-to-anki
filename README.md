# League to Anki

Generate Anki decks from the latest patch notes for League of Legends champions and items in any language
This project uses **Data Dragon** the official and up to date Riot API for game data and assets.

## Supported languages

Below is a list of the languages supported by Data Dragon, which you can also retrieve from the [Data Dragon languages file](https://ddragon.leagueoflegends.com/cdn/languages.json).

| CODE | LANGUAGE |
| ---- | -------- |
| cs_CZ | Czech (Czech Republic) |
| el_GR | Greek (Greece) |
| pl_PL | Polish (Poland) |
| ro_RO | Romanian (Romania) |
| hu_HU | Hungarian (Hungary) |
| en_GB | English (United Kingdom) |
| de_DE | German (Germany) |
| es_ES | Spanish (Spain) |
| it_IT | Italian (Italy) |
| fr_FR | French (France) |
| ja_JP | Japanese (Japan) |
| ko_KR | Korean (Korea) |
| es_MX | Spanish (Mexico) |
| es_AR | Spanish (Argentina) |
| pt_BR | Portuguese (Brazil) |
| en_US | English (United States) |
| en_AU | English (Australia) |
| ru_RU | Russian (Russia) |
| tr_TR | Turkish (Turkey) |
| ms_MY | Malay (Malaysia) |
| en_PH | English (Republic of the Philippines) |
| en_SG | English (Singapore) |
| th_TH | Thai (Thailand) |
| vi_VN | Vietnamese (Viet Nam) |
| id_ID | Indonesian (Indonesia) |
| zh_MY | Chinese (Malaysia) |
| zh_CN | Chinese (China) |
| zh_TW | Chinese (Taiwan) |

## Usage

```bash
pip install -r requirements.txt
python main.py
```

### CLI Options

| Option | Description |
|--------|-------------|
| `--lang`, `-l` | Language locale (e.g. `en_US`, `ko_KR`) |
| `--output`, `-o` | Output `.apkg` filename |
| `--champions` | Only include specific champions (space-separated) |
| `--exclude` | Exclude specific champions (space-separated) |
| `--no-items` | Skip the item deck |
| `--workers` | Parallel workers for fetching (default: 20) |

### Configuration

All options in `config.json` are optional. CLI flags override config values.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `language` | string | `"en_US"` | Language locale |
| `items` | bool | `true` | Include item deck |
| `champions_only` | string[] | — | Whitelist champions |
| `champions_exclude` | string[] | — | Exclude champions |
| `output` | string | auto | Output filename (`LoL_{patch}_{lang}.apkg`) |
| `deck_name` | string | `"League of Legends"` | Anki deck name |
| `champion_card` | object | — | Section layout for champion cards |
| `item_card` | object | — | Section layout for item cards |

#### Customizing card sections

Both `champion_card` and `item_card` accept `front` and `back` arrays to control which sections appear on each side of the card.

**Champion sections:** `header`, `abilities`, `lore`, `stats`, `info`, `tips`

**Item sections:** `header`, `stats`, `description`, `build_path`, `gold`

Example — show lore on front and tips on back:

```json
{
    "champion_card": {
        "front": ["header", "lore"],
        "back": ["header", "stats", "tips"]
    }
}
```
