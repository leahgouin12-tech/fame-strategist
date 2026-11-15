"""The app-store half: what packages genuinely exist on this machine, and the listing files an
alternative store can read.

Two modules, one rule. `inventory` only reports files that are actually sitting in
`data/packages`, and `altsource` only writes a listing entry for a build that is really there -
never a promise of an .ipa that has not been compiled. Everything is served by her own machine on
`/store`, because hosting is the part she refused to pay for and the part no alt store will do for a
LAN app.

The constraint both files keep repeating: this app's brain is the PC. A package is a shell that
opens the local server, so a listing is honest only while it says so. `inventory` reads the same
`state_dir` the rest of the app writes to, so packages live beside her database and nowhere else.
"""
