# AppForge

Ek command se koi bhi app bana do.

```bash
appforge "ek todo app banao"
appforge "snake game banao" --run
appforge "expenses ke liye REST api banao" -o ~/projects/expenses
appforge agent "flask blog banao aur tests likhkar pass karao"   # autonomous mode
appforge ui                                                      # browser me chat
appforge chat                                                    # terminal me chat
```

AppForge aapke prompt ko ek poore project me badal deta hai — saari files, ek README,
aur chalane ki command. Prompt Hindi, English ya Hinglish, kisi me bhi likh sakte hain.

**Poori tarah private:** AI aapke apne computer par chalta hai (Ollama). Koi API key nahi,
koi subscription nahi, aur aapka code kahin bahar nahi jata.

## Setup (ek baar)

```bash
git clone <this-repo> && cd appforge
./install.sh
```

`install.sh` Ollama install karta hai, ek free coding model (`qwen2.5-coder:3b`, ~2 GB)
pull karta hai, aur `appforge` command install kar deta hai. Python 3.9+ ke alawa koi
runtime dependency nahi hai.

Sab theek hai ya nahi:

```bash
appforge --status
```

## Chat — bas baat kariye

```bash
appforge ui          # browser me chat (http://127.0.0.1:7788 apne aap khulta hai)
appforge chat        # wahi cheez terminal me
```

Aap normal bhasha me likhiye, Forge normal bhasha me jawab deta hai — Hindi, Hinglish ya
English, jis me aap likhein. Aur jab kaam ki baat ho to sirf batata nahi, **karta bhi hai**:

| Aap likhte hain                                | Forge kya karta hai                             |
| ---------------------------------------------- | ----------------------------------------------- |
| "tum kaun ho?", "python kahan se seekhun?"      | bas jawab deta hai, koi file nahi banti          |
| "ek dice roller page bana do"                   | poora app likh deta hai aur chalane ki command deta hai |
| "is folder me tests likhkar pass karao"         | agent chalu — files likhta, commands chalata, errors khud fix karta hai |

Har step chat me live dikhta hai. Kaam aapke folder (default `~/AppForge`, `-o` se badlein)
ke andar hi hota hai, aur server sirf `127.0.0.1` par sunta hai — sab kuch aapke PC par.

Browser wala page poora workbench hai — sab kuch dekh bhi sakte hain aur likh bhi:

- **Files** (left): folder ki saari files; click karte hi khul jati hain.
- **Editor**: file me khud change karo aur **Save** — seedha disk par likh jata hai.
- **Terminal** (neeche): `ls`, `python3 app.py`, `pytest` — jo chahe chalao, output wahin dikhega.
  Khatarnak commands (`sudo`, `rm -rf /`...) yahan bhi block hain, aur sab kuch workspace
  folder ke andar hi chalta hai.
- **Chat**: jo bhi Forge banata ya badalta hai, file list turant refresh ho jati hai.

Options: `--port N`, `-o DIR`, `--model M`, `--no-browser` (aur `appforge chat -C DIR`).

## Agent mode — bade task ek command me

```bash
appforge agent "flask blog banao, sqlite ke saath, aur unittest likhkar pass karao"
appforge agent "is folder ke code me README aur tests add karo" -C ~/projects/myapp
```

Ye normal generation se aage hai: agent khud **plan** banata hai, **files likhta hai**,
**commands chalata hai**, output padhta hai, **errors khud fix karta hai**, aur tab tak
chalta hai jab tak kaam verify na ho jaye. Har step screen par dikhta hai aur
`.appforge/agent-log.jsonl` me save hota hai.

Safety (built-in, hamesha on):

- Sirf workspace folder ke andar likh sakta hai — `..` ya `/etc` jaise paths block.
- Khatarnak commands block: `rm -rf /`, `sudo`, `mkfs`, `shutdown`, `curl | sh`, force push...
- Har command par timeout, aur `--max-steps` se step limit.
- `--ask` lagayein to har command chalane se pehle aapse poochega.

Jhooth pakadne ke liye checks: Python file likhte hi syntax check hota hai, "Ran 0 tests"
ko pass nahi maana jata, aur agent tab tak `finish` nahi kar sakta jab tak usne apna code
chalakar dikhaya na ho.

Options: `-C DIR`, `--model M`, `--max-steps N`, `--timeout SEC`, `--ask`.

Agent mode model par sabse zyada depend karta hai. 3B model chhote kaam theek karta hai;
bade multi-file task ke liye `ollama pull qwen2.5-coder:7b` (ya 14B, agar RAM ho) behtar hai:

```bash
appforge agent "..." --model qwen2.5-coder:7b
```

## Teen modes

| Mode         | Kab chalta hai                          | Kya karta hai                                     |
| ------------ | --------------------------------------- | ------------------------------------------------- |
| **Local AI** | Ollama chal raha ho (default)           | aapke PC par model se poora custom project banta hai |
| **Cloud AI** | koi API key env me set ho               | Anthropic / OpenAI / Gemini se project banta hai   |
| **Offline**  | AI available na ho, ya `--offline`      | built-in templates se turant app banta hai         |

Agar local model kharaab jawab de (jaise sirf README), AppForge ek baar dobara try karta
hai aur phir bhi na bane to template par gir jata hai — output hamesha chalne wala app hota
hai. `--strict` se ye fallback band ho jata hai.

## Model badalna

```bash
ollama pull qwen2.5-coder:7b        # bada model = behtar code (zyada RAM)
appforge "..." --model qwen3:4b     # ek baar ke liye
export APPFORGE_MODEL=qwen3:4b      # hamesha ke liye
```

Jo model pehle se pulled hai wahi apne aap chun liya jata hai. Doosre PC par chal rahe
Ollama ko use karna ho to `export OLLAMA_HOST=192.168.1.5:11434`.

## Cloud key (optional)

```bash
export ANTHROPIC_API_KEY=sk-...      # ya OPENAI_API_KEY / GEMINI_API_KEY
appforge "..." --provider anthropic
```

## Options

```
appforge "<prompt>" [options]

  -o, --out DIR       output directory (default: app ke naam ka folder)
      --provider P    ollama | anthropic | openai | gemini
      --model M       model override (jaise qwen3:4b)
      --offline       AI skip karke templates se banao
      --kind K        offline template type (crud, landing, api, cli, game)
      --run           banane ke baad app chala do
      --dry-run       sirf plan dikhao
      --json          app spec JSON me print karo
      --force         maujood files overwrite karo
      --strict        AI fail ho to template par mat giro
      --status        kaunsa AI available hai
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
