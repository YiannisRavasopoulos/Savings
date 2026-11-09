# Themes and appearance

[← Savings](../README.md) · [All docs](README.md)

## Themes

Settings → **Appearance** has **Auto** (the default, follows your device's light/dark mode),
**Light**, **Dark**, **Glass** and **Glass Dark**. All use the app's green accents. The choice is saved per user, so all your
devices use the same one.

**Glass** is a white, iOS-style theme. It keeps the app's own green for buttons, links and
gains, with Apple's system greys and chart colours. Panels, cards, the top bar and the menus are
white frosted glass with a bright rim: see-through, blurring a soft glare of the app's green (with a
touch of light purple) behind the page, catching light along their top edge. It follows iOS conventions:
large bold page titles, small uppercase labels, grey-filled borderless fields, green-tinted
buttons, a segmented control with a sliding white thumb, toggle switches instead of checkboxes,
hairline separators and thin progress bars. Inputs, dropdowns and
their open lists stay solid, so text is always on a plain background. Browsers that can't blur get
solid panels instead. Glass is always light; it doesn't switch with the device.

**Glass Dark** is the same iOS glass look in dark. It has iOS dark greys, white text and the
app's green (brighter green for links, gains and tinted buttons). Behind the dark frosted panels
is a smooth graphite gradient, charcoal at the top to black at the bottom, with one soft glow of
the app's green behind the top of the screen.
Switches have white knobs. As a home-screen app on iPhone it draws behind the status bar, like Dark.

To add a theme, drop a `.css` file into `app/static/themes/` and rebuild
(`./start-savings-server.sh`). It shows up in the picker under its file name. A theme only sets
colour variables (the glass look is the one exception: `style.css` turns it on for the Glass theme), and it's loaded on top of `light.css`, so it only needs to set the ones it
changes. See `dark.css` for the full list. `tests/test_themes.py` checks that themes only use known
variables, and checks the light and dark themes for readable contrast.

## Appearance on this device

Settings → Appearance also has settings saved **on that device only**, so your phone and PC
can differ:

- **Text size:** small, normal or large.
- **Compact lists:** tighter rows in the Log, Month and Year tables, and smaller panels and cards.
- **Privacy mode:** amounts and charts are blurred until you tap them. The first tap reveals the
  amount (and doesn't follow a link it's in). Amounts stay visible until you leave the page.
- **Home layout:** tick which Home sections show (Left over; Income · Spent · Budget used; Where
  it went; Budgets; Last 6 months; Recent) and move them up or down. **Reset to default** puts
  them back.

## Animations

- **Splash screens:** when you open the **home-screen app** (never in a browser tab), one of seven
  splashes plays, once per launch. A tap skips it.
  1. **Tumbling letters:** the logo and the letters of "Savings" fall, tumbling, and bounce into
     place.
  2. **Coin rain:** € coins pile up and turn into the logo, then the name types itself out.
  3. **Filling up:** the logo fills with green like liquid, then the letters pop up one by one.
  4. **Slot machine:** each letter spins like a reel and stops on its letter, left to right.
  5. **Typewriter:** "Savings" types out with a blinking cursor, and a "SAVED" stamp thumps down
     underneath.
  6. **Rising chart:** a green line draws a rising chart that turns into the logo.
  7. **Vault:** the logo appears, the vault door behind it unlocks and swings open, and the view
     zooms past the logo into the dark inside, fading into the app.

  - **Which one:** Settings → Appearance → **Splash screen**: **Rotate daily** (the default, in
    the order above), **Shuffle daily** (a scrambled but fixed order), or always the same one.
    **Play** shows it right away. The choice is saved per device, and the day changes at midnight.
  - **Special days** (with Rotate or Shuffle):
    - **24 December – 1 January:** a Christmas splash. Snow falls, the logo lands and a Santa hat
      drops onto it, and the letters hang from a garland as swinging red, green and gold baubles.
      The greeting is "Merry Christmas!" until the 30th and "Happy New Year!" on the 31st and the 1st.
    - **The first day of each budget period:** the Vault, with "A new period begins".
  - **Trying them on the PC:** `./preview-splashes.sh` builds a page from the app's own splash
    files and opens it in your browser. Pick a splash from the list, it plays, and you're back at
    the list. It also has "Play all in turn", a dark-theme switch and a phone-width frame. It
    needs only `python3`, with no server or Docker, and writes to `tmp/splash-preview/`.
- **Page changes:** a quick cross-fade between pages. Switching tabs slides in the direction of
  the tab order: Home → Month → Trends → Year slides left, going back slides right. The top bar and
  the bottom bar stay put. This uses the browser's built-in page transitions (recent Chrome,
  Android, and Safari on iOS 18.2+). Other browsers simply change page.
- **Logging money:**
  - **an expense** (full form or quick add) gives a red pulse from the screen edges, a short
    shake and a floating "−€12.50";
  - **income** gives a green glow, a small lift and "+€50.00".

  On Home, the "Left over" number counts to its new value. The effect is the confirmation: no
  "Saved" banner or bar appears, even with animations off. Screen readers still announce "Saved".
- **Buttons** press in slightly when tapped.
- **Turning it off:** Settings → Appearance → **Animations** (saved on that device only). If the
  device is set to reduce motion, everything stays off automatically.

All of it is CSS and small scripts (`app/static/splash.css`, `app/static/fx.js`), with no images or downloads.
