---
name: "keepwarm"
description: "Shorthand for /reprompt keepwarm. Use when the user types /keepwarm with an optional level (high by default, or low), or /keepwarm stop. Optional: install it only if you want the shorthand; the reprompt skill works without it."
---

# /keepwarm

Treat `/keepwarm <level>` exactly as `/reprompt keepwarm --<level>`. With no level the default is high. `/keepwarm stop` is `/reprompt stop`.

Load the reprompt skill and follow its sections "The command" and "Arming a loop". Typing this command is the user's word to arm that loop, exactly as if they had named it in a sentence.
