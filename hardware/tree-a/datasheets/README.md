# Datasheets (local only)

Vendor PDFs are not committed (copyright, public repo). Each part card in `../parts/<MPN>.yaml` names the maker URL and revision; download into `datasheets/<part>/`.

## Source list (what was read, 2026-11-23)
| Folder | Document | Where it came from | Card |
|---|---|---|---|
| `tps63900/` | TI SLVSET3D (Oct 2020) | ti.com | `TPS63900DSKR` |
| `MCP73831/` | Microchip DS20001984H | microchip.com | `MCP73831T-2ACI-OT` |
| `2450AT18A100E/` | Johanson detail spec 12/22/2017 (-AEC variant sheet) | johansontechnology.com | `2450AT18A100E` |
| `2450AT42A100E/` | Johanson detail spec 01/25/2012 | johansontechnology.com | `2450AT42A100E` |
| `XL-1010RGB-YG/` | XINGLIGHT data sheet, no revision | LCSC copy | `XL-1010RGB-YG` |
| `HC-TYPE-C-6P-01A/` | maker drawing REV A sheet 1/2 | LCSC copy | `HC-TYPE-C-6P-01A` |
| `TC2030-NL/` | Tag-Connect footprint Rev B, CTX leaflet | tag-connect.com | `TC2030-NL` |
| `nrf54l15-hwdesign/qfaa-reference-layout-0_8/` | Nordic reference schematic, BOM, layout v0.8 | Nordic hardware design package | `nRF54L15-QFAA` |
| `nrf54l15-spec/` | EMPTY: Product Specification PDF not obtainable (Cloudflare 403). The cards tag its values `unverified` | - | `nRF54L15-QFAA` |
| `XL7EL89CKI-111YLC-32M/` | YXC YSX211SL series sheet (1 page) | LCSC copy | `XL7EL89CKI-111YLC-32M` |
| `ABS06-32.768KHZ-9-1-T/` | Abracon ABS06, revised 11-23-20 | abracon.com | `ABS06-32.768KHZ-9-1-T` |
| `SWPA252012S2R2MT/` | Sunlord SWPA series catalog 2023 | LCSC copy | `SWPA252012S2R2MT` |
| `WPN201610H2R2MT/` | Sunlord WPN series catalog 2023 | LCSC copy | `WPN201610H2R2MT` |
| `MPL2012S4R7MHT/` | Sunlord MPL series, revised 2011/03/15 | LCSC copy | `MPL2012S4R7MHT` |
| `BH-AAA-B5AA001/` | MYOUNG drawing MY-CP-0144 2018-09-09 | LCSC copy | `BH-AAA-B5AA001` |
| `SI2301CDS/` | Vishay 68741 Rev C (25-Oct-10) | LCSC copy of the Vishay sheet | `SI2301CDS` |
| `HC-PM254-8.5H-2x4PS/`, `HX-PM2.54-2x4P-TP/`, `Boom-2.54-2x4P-SMD/`, `HX-PZ2.54-2x4P-TP/` | header drawings | LCSC copies | header cards |
| `HX-3x4x2-2P-1.6N/` | Hanxia approval spec of the -04 variant | atta.szlcsc.com copy | `HX-3x4x2-2P-1.6N` |
| `CL21A226MAQNNNE/`, `CL10A106KP8NNNC/` | Samsung MLCC catalog (no per-part curves) | LCSC copy | capacitor cards |
| `Energizer-E92/` | Energizer EN92 data sheet (AAA alkaline, capacity chart) | data.energizer.com | `board.yaml` `design.cell` |
| not obtained | Everlight 18-239A (alternate LED), nRF54L15 PS PDF | LCSC returned HTML / Cloudflare | - |

## Download notes
- `wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/<name>.pdf` returns the PDF; `www.lcsc.com/datasheet/...` returns an HTML page. A `<script>window.top.location.href=...` answer holds the real URL: fetch that once.
- Check the `%PDF` header on every download. Each download goes into its own folder.
