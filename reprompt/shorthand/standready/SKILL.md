---
name: "standready"
description: "Shorthand for /reprompt standready. Use when the user types /standready with an optional level (low by default, or mid or high), or /standready stop. Optional: install it only if you want the shorthand; the reprompt skill works without it."
---

# /standready

Treat `/standready <level>` exactly as `/reprompt standready --<level>`. With no level the default is low. `/standready stop` is `/reprompt stop`.

Load the reprompt skill and follow its sections "The command" and "Arming a loop". Typing this command is the user's word to arm that loop, exactly as if they had named it in a sentence.
