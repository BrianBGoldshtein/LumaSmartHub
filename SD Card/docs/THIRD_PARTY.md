# Third-party materials and maintenance

This is a private appliance candidate, not a reviewed public redistribution. Retain these notices and accompanying source when moving the delivery. The inventory is provenance, not legal clearance or a vulnerability certification.

## Included notices and corresponding source

- React and React DOM share the installed MIT notice; it accompanies the current archive as `image/tailscale-20260926/REACT-LICENSE.txt`. Keep this documentation with the archive. The minified frontend is not the authoritative license text.
- Lucide ISC and the four local font SIL Open Font License notices are in `source/frontend/public/licenses/`, copied into the built frontend and image. Fonts are local, not fetched from a font CDN at runtime.
- Vosk's Apache2.0 notice and Tailscale's upstream BSD3-Clause notice are in `source/assets/licenses/` and `/opt/luma/licenses` in the image.
- New source dependency pyvesync3.4.2 uses the MIT notice in `source/assets/licenses/PYVESYNC-LICENSE.txt`, copied from the installed wheel. It is not yet included in the historical image; preserve this and installed transitive dependency notices in the next image inventory. See ROOM_DEVICES.md for the pinned library/adapter boundary.
- The modified wvkbd keyboard includes its exact original source tarball, patch, build recipe and COPYING/COPYING_WESTON/LICENSE files at `/opt/luma/third-party/wvkbd`. It is not presented as proprietary Luma code.
- The original ReSpeaker overlay source is retained in `source/assets/overlays/` and the image's `/opt/luma-source/assets/overlays/`; the operating system includes standard license texts under `/usr/share/common-licenses`.
- OS package copyright notices remain under `/usr/share/doc`; Python distribution notices remain in the installed packages/metadata. The SPDX inventory records2721 package entries and37908 file entries, not2721 manually reviewed licenses.

Tailscale's pinned release also documents its [CLI/daemon dependency notices](https://github.com/tailscale/tailscale/blob/v1.102.4/licenses/tailscale.md). This upstream list includes platform-dependent dependencies; it must not be interpreted as an exact ARM64 link map. Before any public/commercial redistribution, gather/review corresponding notices and source obligations for that exact release and all OS components. Do not claim the bundled top-level BSD notice licenses every third-party component.

## Updates

Keep the delivered image/checksum/manifests together. The source generator and downloaded large assets are pinned, but apt and Python dependency ranges are not a bit-for-bit package lock. The delivered archive is the reproducible reference artifact; a later rebuild needs fresh tests and a new inventory.

Tailscale is a pinned static binary, not self-updating. Review upstream security releases and update the version and checksum together. Rebuild and test; do not run a generic installer that replaces the dedicated service/firewall. The campus CA profile likewise requires review before its intermediate expires in January2028 or whenever Stanford changes its profile. Application, browser and OS updates also need reviewed maintenance; this is not a promise of unattended lifetime patching.
