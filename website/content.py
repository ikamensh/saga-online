"""Website copy and curated media for each game; release facts come from the catalog.

Screenshots under website/media are inspected frames of the shipping builds
(copied from the games' verification evidence), not mock-ups. Keep claims
aligned with each game's release notes and its About text.
"""

MEDIA = 'website/media'

GAMES = {
    'hellward': {
        'tagline': 'A gothic tower defence in 3D whose demon leaders curse your towers.',
        'summary': ('Hold twelve sanctuaries in two acts, from burning Tristram through Hell\'s Gate to the Temple of '
                    'Light. The demons\' leaders read the fight: before each curse a leader plays the battle ahead in '
                    'its head, again and again, and lays the curse where it hurts your defence most.'),
        'online': None,
        'features': [
            'Twelve locations in two acts, each with its own map, entrances, waves and music.',
            'Leaders that choose their curses by simulating the fight ahead; break their chants with Smite or the Frozen Orb, or Cleanse a cursed tower.',
            'Seven tower families, warded gates, four spells, and forged tower patterns from salvage and side-entrance trophies.',
            'A skill tree paid in sigils, unlearned for free between defences.',
            'A painted story told in pages between the battles, and a prologue comic.',
            'Several campaign profiles, saved on your computer; no account and no internet needed.',
        ],
        'first_title': 'Your first defence',
        'first_match': [
            'Descend from the title: the prologue plays, then the lantern walks to Tristram.',
            'Read who comes and what they curse in the intro, then Defend.',
            'Press 1 and click bare ground beside a lane to raise an Arrow Tower; spread them out.',
            'Press Space to call a wave early for a little gold; click a cursed tower and press C to Cleanse it.',
            'Keep the sanctuary\'s life: ten lives earn two sigils, eighteen earn three.',
        ],
        'screenshots': [
            (f'{MEDIA}/hellward/01-battle.jpg', 'Tristram: the Fallen pack round its Shaman while a Cleanse lifts a curse'),
            (f'{MEDIA}/hellward/02-curse.jpg', 'A Fallen Shaman lays Weaken on an Arrow Tower; its rune circle marks the towers caught'),
            (f'{MEDIA}/hellward/03-map.jpg', 'The Descent: the lantern on the map of Act I'),
            (f'{MEDIA}/hellward/04-briefing.jpg', "The Catacombs' intro: the host, their curses and your arsenal"),
            (f'{MEDIA}/hellward/05-hells-gate.jpg', "Hell's Gate: a warded gate holds and the Bone Acolyte's curse is broken"),
        ],
        'requirements': {
            'windows': 'Windows 10 or 11, 64-bit, with Vulkan or Direct3D 12 graphics.',
            'macos': 'macOS 14 or later on Apple Silicon (M1 or newer).',
        },
        'known_issues': [
            'An early preview: some monsters and towers of the later locations still wear stand-in bodies borrowed from others.',
            'The Windows build is unsigned and the Mac app is not notarized; see the first-launch notes above.',
            'English only.',
        ],
        'guide': 'https://github.com/ikamensh/hellward#readme',
        'support': 'https://github.com/ikamensh/hellward/issues',
        'source': 'https://github.com/ikamensh/hellward',
        'font_note': '',
        'data_dir': {'windows': '%USERPROFILE%\\.hellward', 'macos': '~/.hellward'},
    },
    'warband': {
        'tagline': 'A snappy real-time strategy skirmish in the classic mould.',
        'summary': ('Gather gold and lumber, raise a base, train an army and raze the rival settlement. '
                    'Matches take ten to twenty minutes against an AI that plays a recognisable strategy, '
                    'or against a friend over the internet.'),
        'online': {
            'mode': 'Two-player competitive match',
            'text': ('Two seats per room. Create a room, send the code or invitation link to your friend, and the '
                     'match starts when you both connect. The server runs the simulation; a dropped connection '
                     'pauses the match and reconnects automatically.'),
            'retention': 'Rooms stay open for 15 minutes without both players.',
        },
        'features': [
            'Four races: humans, orcs, elves and dwarves share seven unit roles and nine buildings, each with its own numbers, a passive trait, two race-only upgrades, look and voice.',
            'Painted sprites for every unit and building; units stride, wind up and swing, and arrows and stones fly and land where they were aimed.',
            'Settlement planning: queue buildings, units and upgrades without selecting a worker, with a production overview when nothing is selected.',
            'Idle peasants find safe work on their own; construction plans borrow gatherers after delivery.',
            'Five map layouts in three sizes and three lands, generated fresh for every match with meadows, groves, ponds and stone.',
            'Four AI difficulties with measured ratings for offline games with two to four factions; autosave every two minutes.',
            'Original art and audio made for the game: sprites painted from its own low-poly renders, generated impacts, cries and collapses, and synthesised music.',
        ],
        'first_match': [
            'Let your peasants gather. Gold and lumber totals are at the top of the screen.',
            'In the Settlement row choose Build → Farm and click clear ground near your base.',
            'Build a Barracks, then Train → Footman. Requests wait until they can be paid.',
            'Select your soldiers, press A and click towards the enemy to attack-move.',
            'Eliminate every enemy unit and building to win.',
        ],
        'screenshots': [
            (f'{MEDIA}/warband/01-battle.png', 'A pitched battle between the humans and the elves outside a farm row'),
            (f'{MEDIA}/warband/02-orc-settlement.png', 'An orc settlement eight minutes in: pig farms, war camp, forge, kennels and sawmill'),
            (f'{MEDIA}/warband/03-elf-train-plans.png', 'The Train card of an elf settlement in an online match, from the shipping Mac build'),
            (f'{MEDIA}/warband/04-title.png', 'The title screen over a winter map'),
        ],
        'requirements': {
            'windows': 'Windows 10 or 11, 64-bit, with OpenGL 3.3 graphics drivers. About 160 MB on disk.',
            'macos': 'macOS 14 or later on Apple Silicon (M1 or newer). About 160 MB on disk.',
        },
        'known_issues': [
            'The installer is unsigned and the Mac app is not notarized; see the first-launch notes above.',
            'The layout uses a fixed logical canvas; fullscreen helps readability on small screens.',
            'Large offline maps with three or four players can run past twenty minutes without a decision.',
            'English only.',
        ],
        'guide': 'https://github.com/ikamensh/warband/blob/main/docs/warband-play-together.md',
        'data_dir': {'windows': '%USERPROFILE%\\.warband', 'macos': '~/.warband'},
    },
    'tribes': {
        'tagline': 'A compact turn-based strategy game on an isometric island.',
        'summary': ('Lead a tribe across a small isometric map: found cities, research technologies, harvest '
                    'the land and outfight rival tribes within thirty rounds. Every action has a hotkey and '
                    'a match fits in a lunch break.'),
        'online': {
            'mode': 'Two-player competitive match',
            'text': ('Two human tribes take alternating turns on a server-owned map. Create a room, share the '
                     'code, and play at your own pace; the turn waits for you while you are connected.'),
            'retention': 'Rooms stay open for 15 minutes without both players.',
        },
        'features': [
            'Cities, parks, technologies, territory and a surviving army all count towards the final score.',
            'A tech tree that changes how you harvest, move and fight.',
            'AI tribes that recruit, research and concede when they cannot rebuild.',
            'High scores recorded locally, with a results screen that explains every point.',
            'Keyboard-first controls: the keycaps on screen show every shortcut.',
        ],
        'first_match': [
            'Select your warrior with Enter and move it to explore the island.',
            'Press T to open the technology list and pick the first research.',
            'Capture neutral villages with C to grow your tribe.',
            'End your turn with E; the game shows whose turn it is at the top.',
            'Hold the most cities and the largest empire when round 30 ends.',
        ],
        'screenshots': [
            (f'{MEDIA}/tribes/01-tribes-match.png', 'An online match seen from the Ember tribe'),
            (f'{MEDIA}/tribes/02-tribes-title.png', 'The Tribes title screen'),
            (f'{MEDIA}/tribes/03-tribes-result.png', 'A results screen with the final standings'),
        ],
        'requirements': {
            'windows': 'Windows 10 or 11, 64-bit, with OpenGL 3.3 graphics drivers.',
            'macos': 'macOS 14 or later on Apple Silicon (M1 or newer).',
        },
        'known_issues': [
            'The installer is unsigned and the Mac app is not notarized; see the first-launch notes above.',
            'Online matches are two human tribes only; offline games add AI tribes.',
            'English only.',
        ],
        'guide': 'https://github.com/ikamensh/saga2d/blob/main/docs/online-multiplayer.md',
        'data_dir': {'windows': '%USERPROFILE%\\.tribes', 'macos': '~/.tribes'},
    },
    'shardbound': {
        'tagline': 'An Eador-inspired campaign of provinces, heroes and hex battles.',
        'summary': ('Lead one of four heroes and a persistent army through a linked campaign of three shards. '
                    'Develop your stronghold, investigate guarded sites, counter a rival expedition and '
                    'command turn-based hex battles where veterans keep their experience.'),
        'online': {
            'mode': 'Two-player shared-realm co-op',
            'text': ('You and a friend command the same realm and army. Either of you can build, explore and '
                     'give battle orders; the server keeps one authoritative campaign. Campaign rooms are kept '
                     'for seven days without both players, so you can continue tomorrow.'),
            'retention': 'Campaign rooms are kept for 7 days without both players.',
        },
        'features': [
            'Four heroes with two advancement disciplines each, ten troop roles and twelve relics.',
            'Guarded expeditions with rout, hold and extraction objectives across twelve authored patterns.',
            'Manual orders or optional automatic rounds, with skippable playback of the resolved actions.',
            'A three-shard linked campaign: choose the next challenge and which veterans and relics travel.',
            'Three world themes, seed selection and three difficulty settings.',
            'Manual saves, rolling autosaves, sound controls, reduced motion and larger reading text.',
        ],
        'first_match': [
            'Open the Field Guide with F1 for your first turns; the Codex (C) holds every rule.',
            'Build a marketplace to fund your army and recruit troops at your stronghold.',
            'Explore the current province with X and inspect the rival plan with V.',
            'Invade a neighbouring province and fight the hex battle, or let automatic rounds resolve it.',
            'Capture Duskspire before the rival takes Westwatch.',
        ],
        'screenshots': [
            (f'{MEDIA}/shardbound/01-portable-smoke-shard.png', 'The Frontier shard with the province map and stronghold'),
            (f'{MEDIA}/shardbound/02-portable-smoke-battle.png', 'A hex battle for Silverford'),
            (f'{MEDIA}/shardbound/03-portable-smoke-codex.png', 'The Codex rules reference'),
            (f'{MEDIA}/shardbound/04-portable-smoke-rival.png', 'The rival expedition plan'),
        ],
        'requirements': {
            'windows': 'Windows 10 or 11, 64-bit, with OpenGL 3.3 graphics drivers.',
            'macos': 'macOS 14 or later on Apple Silicon (M1 or newer).',
        },
        'known_issues': [
            'A development preview: balance, onboarding and presentation are still being evaluated, and the app uses a development icon.',
            'The installer is unsigned and the Mac app is not notarized; see the first-launch notes above.',
            'Co-op shares one realm; there is no competitive online mode yet.',
            'English only.',
        ],
        'guide': 'https://github.com/ikamensh/saga2d/blob/main/eador/README.md',
        'data_dir': {'windows': '%USERPROFILE%\\.shardbound', 'macos': '~/.shardbound'},
    },
}

SUPPORT_URL = 'https://github.com/ikamensh/saga2d/issues'
SOURCE_URL = 'https://github.com/ikamensh/saga2d'
