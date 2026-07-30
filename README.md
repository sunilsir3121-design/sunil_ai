# AppForge

Ek command se koi bhi app bana do.

```bash
appforge "ek todo app banao"
appforge "snake game banao" --run
appforge "expenses ke liye REST api banao" -o ~/projects/expenses
```

AppForge aapke prompt ko ek poore project me badal deta hai — saari files, ek README,
aur chalane ki command. Prompt Hindi, English ya Hinglish, kisi me bhi likh sakte hain.

## Do modes

| Mode        | Kab chalta hai                        | Kya karta hai                                   |
| ----------- | ------------------------------------- | ----------------------------------------------- |
| **AI**      | env me LLM API key mile               | model se poora custom project generate hota hai |
| **Offline** | key na ho, ya `--offline` diya ho     | built-in templates se chalta-phirta app banta hai |

Dono modes bilkul ek jaisa output dete hain, isliye bina key ke bhi CLI kaam karta hai.

## Install

```bash
git clone <this-repo> && cd appforge
pip install -e .
```

Koi runtime dependency nahi hai — sirf Python 3.9+.

## API key (optional, AI mode ke liye)

```bash
export ANTHROPIC_API_KEY=sk-...      # ya
export OPENAI_API_KEY=sk-...         # ya
export GEMINI_API_KEY=...
```

Key set karte hi AI mode apne aap on ho jata hai. Provider force karna ho to
`--provider openai` ya `APPFORGE_PROVIDER=openai`.

## Options

```
appforge "<prompt>" [options]

  -o, --out DIR       output directory (default: app ke naam ka folder)
      --provider P    anthropic | openai | gemini
      --model M       model override
      --offline       AI skip karke templates se banao
      --kind K        offline template type (crud, landing, api, cli, game)
      --run           banane ke baad app chala do
      --dry-run       sirf plan dikhao
      --json          app spec JSON me print karo
      --force         maujood files overwrite karo
      --list-templates
```

## Offline templates

| kind      | example prompt                          | stack                          |
| --------- | --------------------------------------- | ------------------------------ |
| `crud`    | "ek todo app banao"                     | HTML + CSS + JS, localStorage  |
| `landing` | "mera portfolio website banao"          | static landing page            |
| `api`     | "items ka rest api banao"               | Python stdlib HTTP server      |
| `cli`     | "ek terminal task manager banao"        | Python argparse CLI            |
| `game`    | "snake game banao"                      | HTML canvas                    |

## Tests

```bash
python3 -m unittest discover -s tests -v
```
