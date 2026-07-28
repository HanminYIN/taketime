# Image Attribution

## pill-organizer.jpg

- Title: Pill Organizer With Vitamins And Medicines
- Creator: Stevepb
- Source: https://commons.wikimedia.org/wiki/File:Pill_Organizer_With_Vitamins_And_Medicines.jpg
- License: CC0 1.0 Universal (Public Domain Dedication)
- License URL: https://creativecommons.org/publicdomain/zero/1.0/
- Local change: resized to a maximum dimension of 1400px and JPEG quality 78

Responsive derivatives are generated from this local source for the history
view. JPEG files use FFmpeg quality 3; AVIF files use SVT-AV1 CRF 30. Both sets
are available at 480px, 800px, and 1400px widths. The original is retained as
the attribution source but is not requested by the application.

The image is illustrative and does not represent any medication in the user's
schedule.

## taketime-mark.svg

- Purpose: TakeTime browser favicon and text brand mark
- Source: project-authored SVG
- Typeface behavior: uses the viewer's installed Chinese Kai-style font, with a generic serif fallback
- External assets: none

## taketime-slogan-serif.woff2

- Purpose: navigation slogan “服药有时，养正无恙”
- Typeface: Noto Serif SC Medium (500)
- Upstream: Noto Serif SC 2.003 from Google Fonts commit `2e61f4355afd22b801791b0df176065082423b87`
- Original file: `ofl/notoserifsc/NotoSerifSC[wght].ttf`
- Text subset source: Google Fonts CSS2 `text=` response for weight 500
- License: SIL Open Font License 1.1
- License file: `OFL-NotoSerifSC.txt`
- Local change: subset to nine total glyphs (eight ideographs plus punctuation), encoded as WOFF2
- SHA-256: `cc0ca9366d6b142aa0b239cfae59d1e5a58c6f8f5997e6562d284fa4ba592bd0`

Reproduction outline:

```sh
curl -G 'https://fonts.googleapis.com/css2' \
  --data-urlencode 'family=Noto Serif SC:wght@500' \
  --data-urlencode 'text=服药有时，养正无恙'
# Download the font URL returned by the CSS response, then encode that
# nine-glyph TrueType payload as WOFF2 with fonttools ttLib.woff2.
```
