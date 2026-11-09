# Shared categories

[← Savings](../README.md) · [All docs](README.md)

A **shared (joint) category** is one category used by several people, for example "Home
groceries" for a household. Create one in **Categories → + Add category → tick "Shared
category"**. You become its **moderator**, and it gets a purple accent everywhere: Categories,
the Add form ("Shared" group), the Log and Home.

**Turning an existing category into a shared one:** on its card in Categories, use **Turn into
shared**.

- **History is unchanged:** its past expenses stay 100 % yours, exactly as they were.
- **Budget:** its budget stays your own (see below).
- **Sharing starts when others join,** on the day they accept.
- **One-way:** it can't be turned back into a personal category, but you can close it later.
  Archived categories must be unarchived first.

Everything in a shared category takes effect **the same day**: joining, leaving, removing,
closing and new shares. There are no shared periods and nothing is scheduled.

## How money is counted

- **Who pays:** whoever logs an expense logs the **full price**, and it's shown as **"Paid by
  <name>"**. Only they can edit or delete it.
- **Shares:** each member has a share (they always add up to 100 %). The default is an equal
  split; the moderator can rearrange it.
- **Counting:** for **each member**, their share of every expense counts as their own cost, in
  their Home, Month, Year, Trends, forecast and budgets, **no matter who paid**. Example: €50 paid
  by Alice with a 60/40 split costs Alice €30 and Bob €20.
- **Which split:** each expense uses the shares in effect **on its own date**. Changing the
  shares affects expenses dated from that day on; earlier ones keep their split.
- **Splitting to the cent:** amounts are split with the [largest remainder method][lrm], so the
  parts always add up exactly. A leftover cent goes to the payer when there's a tie.
- **Settling up** who paid more is up to you in person; "Paid by", and each member's "Paid this
  period" on the shared page, show the facts.

## Budgets are personal

A shared category has **no total budget**. Each member sets **their own budget** for it
(Categories → its card → **Your budget**, or optionally when accepting the invitation), with the
same history rules as any other budget. It's checked in **your own periods** (Month, Home,
Trends) against **your share** of the spending, and it's included in your "Total budget" card.

Budgets are **private**: other members never see yours. The moderator doesn't manage budgets,
only the members, shares and name.

## Members

- **Inviting:** the moderator invites people by their **exact username** (nobody can browse the
  list of users). There are at most 8 members including pending invitations, and an invitation
  expires after 14 days.
- **Accepting:** the invitation appears on Home and Categories. The pop-up explains what joining
  means:
  - you join **today**, and the split becomes equal from today;
  - members see each other's expenses **in this category only**: date, description, amount and
    who paid. Notes and the one-off mark stay private to whoever logged the expense, in the Log
    and in data downloads;
  - you can leave at any time.

  It has an optional field for **your monthly budget**. You must tick "I understand and agree".
  You can also Decline.
- **Leaving and removing** (the moderator can remove members) take effect **today**: the person
  is a member through yesterday. The category becomes **archived for them**: it shows as
  "<name> (left)" in their Month, Log and Categories, they can't add to it, and their past
  expenses and their share of everyone's past expenses stay in their totals. For the remaining
  members all existing expenses stay as they are.
- **Share changes:**
  - when someone joins, the split becomes equal;
  - when someone leaves, their share is shared out among the others **in proportion to their
    shares**, e.g. 60/30/10 without the 10 becomes 66.67/33.33;
  - the moderator can then rearrange it (**Rearrange shares** on the shared page).
- **The moderator** renames it, invites, sets shares, removes members, can **hand over**
  moderation, and can **close** the category. Closing means everyone leaves today; the history
  stays. The moderator can't leave while others stay without handing over first.
- **If the moderator's account is deleted,** moderation passes to the longest-standing member,
  and their share is redistributed from that day. A shared category with nobody and nothing left
  is deleted.
- **Deleting:** a closed shared category that never had an expense shows a **Delete** button to
  its former members; one with expenses stays, since it's part of their history.
- **After each action** (joining, leaving, removing, closing, new shares) a pop-up confirms it,
  and **refused actions** get an error pop-up explaining why.

## Archived names

An archived category gets **"(archived)"** added to its name, e.g. "Car (archived)", so the
original name is free to reuse, and so an invitation to someone else's "Car" never clashes with
it. Unarchiving removes the suffix again, or uses "Car (2)" if you have a new "Car" by then. A
closed or emptied shared category is renamed the same way.

## Reminder before a reset

During the **last 3 days before your period resets**, Home and Categories show a purple banner,
e.g. "Your budget period resets on 28 Nov 2026 (in 2 days). A good time to review your budgets."
**✕** hides it until the next reset; each device remembers that separately.

## How it's stored

- Each expense has an owner (`expenses.user_id`, who paid).
- Each person's cost of each expense is a row in `expense_shares`: one row for a personal
  expense, one per member for a shared one. Every personal total is the sum of your rows.
- Shares are complete splits in `joint_splits`, each effective from a date, the same "history"
  idea as income and budgets.
- Budget entries (`category_budgets`) belong to a person (`user_id`).
- The rules are in `app/joint.py`, the pages in `app/shared.py`, and `tests/test_joint.py` checks
  the cases above with exact numbers.

[lrm]: https://en.wikipedia.org/wiki/Largest_remainder_method
