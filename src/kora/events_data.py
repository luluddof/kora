"""Les evenements de l'age tribal (donnees). Moteur : events.py.

Chaque chaine a un sens : les loups menent (peut-etre) aux chiens ; une
chasse legendaire fait un chef de bande trop admire, qui peut devenir un
rival, puis vouloir partir ; un accueil fait aux etrangers peut revenir
en cadeaux, en mariage ou en vengeance. Aucune suite n'est garantie.

Effets et conditions : voir events.apply / events.check.
Textes : {band} (votre bande / le clan de X), {Band}, {leader}, {chief},
{other}, {pop}, {dead}, {cause}, {savoir}, {butin}, {lieu}.
"""

from __future__ import annotations

from src.kora.events import Event, Follow, Option, Outcome

HUNT_LAND = ("foret", "plaine", "colline", "steppe")

EVENTS: dict[str, Event] = {
    e.id: e
    for e in (
        # --- les loups -> les chiens -------------------------------------
        Event(
            "loups",
            "Les loups rodent",
            "Chaque nuit, les loups tournent plus près du camp de {band}. Ce matin, on a trouve "
            "leurs traces à quelques pas des enfants.",
            conds=(("not_village",), ("season", "automne", "hiver"), ("terrain", *HUNT_LAND), ("stock_lt", 8)),
            weight=0.04,
            cooldown=78,
            mood="danger",
            options=(
                Option(
                    "Organiser une battue",
                    outcomes=(
                        Outcome(
                            0.55,
                            (("prestige", 3), ("renown", 8)),
                            (Follow("loups_peau", 0.5, (2, 5)),),
                            "La battue a réussi : la meute est dispersée.",
                            mods=((("knows", "arc"), 0.15), (("knows", "epieu"), 0.1), (("leader_trait", "chasseur"), 0.1)),
                        ),
                        Outcome(
                            0.45,
                            (("pop", -3, -1), ("loyalty", -5)),
                            (Follow("loups_reviennent", 0.6, (3, 8)),),
                            "La battue tourne mal : des chasseurs ne reviennent pas.",
                        ),
                    ),
                    ai=1.0,
                ),
                Option(
                    "Entretenir de grands feux toute la nuit",
                    effects=(("stock", -1),),
                    follow=(Follow("loups_reviennent", 0.3, (4, 10)),),
                    text="Les feux tiennent les loups a distance, mais la veille et le bois coûtent cher.",
                    ai=1.4,
                ),
                Option(
                    "Lever le camp",
                    effects=(("goto_far", 6, 12),),
                    text="{Band} part chercher un coin plus sur.",
                    ai=0.6,
                ),
            ),
        ),
        Event(
            "loups_reviennent",
            "La grande louve",
            "Les loups sont revenus, plus nombreux. Une grande louve grise les mène, et elle n'a "
            "plus peur du feu.",
            trigger="follow",
            mood="danger",
            options=(
                Option(
                    "Traquer la louve",
                    outcomes=(
                        Outcome(
                            0.45,
                            (("prestige", 5), ("trait", "tueur_loups"), ("renown", 15)),
                            (Follow("loups_peau", 0.7, (1, 4)),),
                            "{leader} a tue la grande louve.",
                            mods=((("knows", "arc"), 0.15), (("leader_trait", "chasseur"), 0.1), (("leader_trait", "guerrier"), 0.1)),
                        ),
                        Outcome(
                            0.55,
                            (("pop", -4, -2), ("loyalty", -10)),
                            (),
                            "La louve s'est échappée, et {band} pleure ses morts.",
                        ),
                    ),
                ),
                Option(
                    "Laisser de la viande loin du camp",
                    effects=(("stock", -2),),
                    follow=(Follow("louveteaux", 0.35, (8, 20)),),
                    text="Chaque soir, on laisse des restes loin du camp. Les loups ne viennent plus si près.",
                    ai=1.3,
                ),
                Option("Partir", effects=(("goto_far", 8, 14),), text="{Band} s'en va.", ai=0.7),
            ),
        ),
        Event(
            "louveteaux",
            "Des louveteaux",
            "Des louveteaux suivent maintenant {band} de loin. Les enfants leur jettent des os ; "
            "l'un d'eux dort déjà près du feu.",
            trigger="follow",
            conds=(("no_flag", "louveteaux"),),
            mood="chance",
            options=(
                Option(
                    "Les garder",
                    effects=(("flag", "louveteaux"),),
                    text="Les jeunes loups grandissent parmi vous. Un savoir devient possible : Chiens de chasse.",
                    ai=1.5,
                ),
                Option("Les chasser", text="On chasse les louveteaux a coups de pierres."),
            ),
        ),
        Event(
            "loups_peau",
            "La peau du grand loup",
            "La peau du grand loup sèche devant l'abri de {leader}. On raconte déjà l'histoire autour du feu.",
            trigger="follow",
            mood="chance",
            options=(
                Option(
                    "{leader} l'offre au chef",
                    effects=(("chief_renown", 5), ("loyalty", 10)),
                    requires=(("not_chief_band",),),
                    text="Le clan de {leader} a offert la peau au chef : les liens se resserrent.",
                    ai=1.2,
                ),
                Option(
                    "{leader} la garde",
                    effects=(("renown", 10), ("loyalty", -5)),
                    follow=(Follow("rivalite", 0.35, (26, 78)),),
                    text="{leader} porte la peau sur ses épaules. On l'admire, peut-être un peu trop.",
                ),
            ),
        ),
        # --- le grand troupeau ---------------------------------------------
        Event(
            "troupeau",
            "Le grand troupeau",
            "Un immense troupeau traverse le pays près de {band}. La terre tremble sous les sabots depuis l'aube.",
            conds=(("not_village",), ("season", "printemps", "automne"), ("terrain", "plaine", "steppe")),
            weight=0.05,
            cooldown=52,
            mood="chance",
            options=(
                Option(
                    "Grande chasse : tout le monde",
                    effects=(("stop",),),
                    outcomes=(
                        Outcome(
                            0.7,
                            (("stock", 6), ("prestige", 2)),
                            (Follow("chasse_legendaire", 0.35, (1, 3)),),
                            "Une chasse dont on parlera longtemps : la viande ne manque plus.",
                            mods=((("knows", "epieu"), 0.1), (("knows", "arc"), 0.1), (("knows", "chiens"), 0.05)),
                        ),
                        Outcome(
                            0.3,
                            (("pop", -2, -1), ("stock", 2)),
                            (),
                            "Un taureau furieux a charge : il y a des blessés et des morts.",
                        ),
                    ),
                    ai=1.5,
                ),
                Option(
                    "Suivre le troupeau",
                    effects=(("stock", 3), ("goto_far", 10, 16)),
                    follow=(Follow("troupeau_familier", 0.4, (8, 16)),),
                    text="{Band} suit le troupeau et vit sur ses traces.",
                ),
                Option("Le laisser passer", text="Le troupeau s'éloigne.", ai=0.4),
            ),
        ),
        Event(
            "troupeau_familier",
            "Des bêtes qui ne fuient plus",
            "À force de les suivre, les bêtes ne fuient plus {band}. Certains jeunes arrivent a les approcher.",
            trigger="follow",
            conds=(("not_knows", "troupeau"),),
            mood="chance",
            options=(
                Option(
                    "Apprendre a les garder",
                    effects=(("tech_progress_id", "troupeau", 0.4),),
                    text="Garder les bêtes plutot que les chasser : le savoir du Troupeau avance.",
                    ai=1.5,
                ),
                Option("Continuer a les chasser", effects=(("stock", 2),), text="La chasse est bonne."),
            ),
        ),
        Event(
            "chasse_legendaire",
            "Une chasse légendaire",
            "{leader} a abattu à lui seul le taureau de tête. Tout le camp chante son nom.",
            trigger="follow",
            mood="chance",
            options=(
                Option(
                    "Célébrer {leader}",
                    effects=(("renown", 15), ("trait", "chasseur"), ("prestige", 2)),
                    follow=(Follow("rivalite", 0.3, (26, 60)),),
                    text="On célèbre {leader}, le grand chasseur.",
                    ai=1.2,
                ),
                Option(
                    "Partager la gloire entre tous",
                    effects=(("loyalty_all", 4),),
                    text="La chasse est l'œuvre de tous : chacun repart fier.",
                ),
            ),
        ),
        # --- rivalite -> le clan qui part ------------------------------------
        Event(
            "rivalite",
            "Un rival",
            "{leader} dit tout haut qu'il mènerait mieux la tribu que {chief}. Dans son clan, certains hochent la tête.",
            trigger="pulse",
            conds=(("not_chief_band",), ("is_rival",)),
            weight=0.03,
            cooldown=104,
            mood="peuple",
            options=(
                Option(
                    "Le désigner héritier",
                    effects=(("heir",), ("loyalty", 20), ("chief_renown", -5)),
                    text="{leader} sera le prochain chef. Son clan est fier.",
                    ai=1.0,
                ),
                Option(
                    "L'humilier devant tous",
                    outcomes=(
                        Outcome(
                            0.5,
                            (("loyalty", -25), ("chief_renown", 10)),
                            (),
                            "{chief} a remis {leader} à sa place. Le clan gronde, mais se tait.",
                            mods=((("chief_trait", "guerrier"), 0.15), (("chief_stronger",), 0.1)),
                        ),
                        Outcome(
                            0.5,
                            (("loyalty", -40),),
                            (Follow("clan_part", 0.5, (4, 12)),),
                            "L'affront est allé trop loin : le clan de {leader} parle de partir.",
                        ),
                    ),
                    ai=0.6,
                ),
                Option(
                    "Lui offrir des honneurs",
                    effects=(("prestige", -5), ("loyalty", 25)),
                    requires=(("prestige_ge", 5),),
                    text="Des présents calment {leader}, pour un temps.",
                    ai=1.2,
                ),
            ),
        ),
        Event(
            "clan_part",
            "Le clan veut partir",
            "Le clan de {leader} ({pop} personnes) veut prendre son propre chemin. Ils disent que "
            "{chief} est trop loin, et qu'ils se débrouilleront seuls.",
            trigger="clan_part",
            mood="danger",
            deadline=10,
            options=(
                Option(
                    "Les laisser partir en paix",
                    effects=(("secede",),),
                    text="Le clan de {leader} s'en va. Ils restent vos parents.",
                    ai=0.8,
                ),
                Option(
                    "Les retenir par des présents",
                    effects=(("prestige", -8), ("loyalty", 30)),
                    requires=(("prestige_ge", 8),),
                    text="Des présents et des promesses : le clan reste.",
                    ai=1.2,
                ),
                Option(
                    "Envoyer le chef leur parler",
                    outcomes=(
                        Outcome(
                            0.45,
                            (("loyalty", 35), ("chief_renown", 5)),
                            (),
                            "{chief} a su trouver les mots : le clan de {leader} reste.",
                            mods=((("chief_trait", "rassembleur"), 0.2), (("near_chief", 6), 0.15), (("chief_trait", "genereux"), 0.1)),
                        ),
                        Outcome(0.55, (("secede", True),), (), "Les palabres ont tourne court : le clan part, fâché."),
                    ),
                    ai=1.0,
                ),
                Option(
                    "Les retenir par la force",
                    outcomes=(
                        Outcome(
                            0.5,
                            (("loyalty_set", 45), ("pop_pct", -0.1), ("prestige", 2)),
                            (),
                            "Il y a eu des coups et des morts, mais le clan de {leader} est reste.",
                            mods=((("chief_stronger",), 0.2), (("chief_trait", "guerrier"), 0.1)),
                        ),
                        Outcome(0.5, (("secede", True), ("prestige", -5)), (), "Le clan s'est battu et s'est enfui : ils ne vous pardonneront pas."),
                    ),
                    ai=0.4,
                ),
            ),
        ),
        # --- les etrangers --------------------------------------------------
        Event(
            "etrangers",
            "Des étrangers",
            "Des inconnus observent {band} depuis la lisière. Ils portent des peaux peintes d'ocre et "
            "parlent une langue étrange : ce sont des {other}.",
            trigger="contact",
            player_only=True,
            conds=(("other_alive",),),
            mood="peuple",
            options=(
                Option(
                    "Leur offrir à manger",
                    effects=(("stock", -1), ("relation", 15)),
                    follow=(Follow("etrangers_cadeaux", 0.5, (4, 12)),),
                    text="Vous partagez le repas. Les {other} repartent en souriant.",
                    ai=1.2,
                ),
                Option(
                    "Les observer de loin",
                    follow=(Follow("etrangers_approchent", 0.35, (2, 6)),),
                    text="Personne ne bouge. Les inconnus disparaissent dans les arbres.",
                    ai=1.0,
                ),
                Option(
                    "Les chasser",
                    effects=(("prestige", 1), ("relation", -20)),
                    follow=(Follow("represailles", 0.4, (3, 8)),),
                    text="Des pierres et des cris : les {other} s'enfuient.",
                    ai=0.3,
                ),
            ),
        ),
        Event(
            "etrangers_cadeaux",
            "Les étrangers reviennent",
            "Les {other} sont revenus, les bras charges. Ils offrent de la viande séchée, et montrent "
            "comment ils font certaines choses.",
            trigger="follow",
            conds=(("other_alive",),),
            mood="chance",
            options=(
                Option(
                    "Accepter et apprendre",
                    effects=(("stock", 2), ("relation", 5), ("tech_progress", 0.25)),
                    text="Les {other} vous ont montre leur savoir-faire.",
                    ai=1.3,
                ),
                Option(
                    "Leur rendre la pareille",
                    effects=(("stock", -1), ("relation", 12)),
                    follow=(Follow("mariage_propose", 0.35, (26, 52)),),
                    text="Des présents contre des présents : on se quitte en amis.",
                ),
            ),
        ),
        Event(
            "etrangers_approchent",
            "Le vieil étranger",
            "Les {other} reviennent, plus près. Un vieil homme s'avance seul, les mains ouvertes.",
            trigger="follow",
            conds=(("other_alive",),),
            mood="peuple",
            options=(
                Option("L'accueillir", effects=(("relation", 10),), text="Le vieil homme mange avec vous.", ai=1.3),
                Option("Le renvoyer", effects=(("relation", -5),), text="Le vieil homme repart sans un mot."),
            ),
        ),
        Event(
            "represailles",
            "Ils n'ont pas oublié",
            "Les {other} n'ont pas oublié l'accueil de {band}. On a vu leurs guerriers se rassembler.",
            trigger="follow",
            conds=(("other_alive",),),
            mood="danger",
            options=(
                Option(
                    "Se préparer au combat",
                    effects=(("flag", "sur_gardes", 8), ("provoke",)),
                    text="On aiguisé les épieux et on veille : que les {other} viennent.",
                ),
                Option(
                    "Envoyer un présent d'excuse",
                    effects=(("stock", -2), ("relation", 15)),
                    text="Le présent est accepté. Les {other} rentrent chez eux.",
                    ai=1.3,
                ),
            ),
        ),
        Event(
            "mariage_propose",
            "Une proposition de mariage",
            "Les {other} proposent d'unir une fille de leur chef à un fils de {chief}. Une alliance, "
            "disent-ils, pour que nos enfants chassent ensemble.",
            trigger="follow",
            conds=(("other_alive",),),
            mood="peuple",
            options=(
                Option("Accepter", effects=(("pact", "alliance"),), text="Les mariages sont célèbres : vous voilà alliés des {other}.", ai=1.3),
                Option("Refuser poliment", effects=(("relation", -5),), text="Les {other} repartent, déçus."),
            ),
        ),
        # --- propositions des autres peuples ---------------------------------------
        Event(
            "offre_treve",
            "Une offre de paix",
            "Des envoyés des {other} arrivent, les mains vides et ouvertes. Ils proposent la paix pour deux ans.",
            trigger="offre_treve",
            player_only=True,
            conds=(("other_alive",),),
            mood="peuple",
            options=(
                Option("Accepter la trêve", effects=(("pact", "treve"),), text="Trêve conclue avec les {other}.", ai=1.2),
                Option("Refuser", effects=(("relation", -5),), text="Vous renvoyez les envoyés des {other}."),
            ),
        ),
        Event(
            "offre_alliance",
            "Une offre d'alliance",
            "Les {other} proposent une alliance, scellée par des mariages entre les familles des chefs.",
            trigger="offre_alliance",
            player_only=True,
            conds=(("other_alive",),),
            mood="peuple",
            options=(
                Option("Accepter l'alliance", effects=(("pact", "alliance"),), text="Vous voilà alliés des {other}.", ai=1.2),
                Option("Refuser", effects=(("relation", -5),), text="Vous déclinez l'offre des {other}."),
            ),
        ),
        Event(
            "offre_commerce",
            "Une offre d'échanges",
            "Des porteurs des {other} arrivent avec du sel, des pots et des étoffes : leur chef propose que "
            "vos villages échangent leurs biens, chaque mois, comme on le fait entre voisins.",
            trigger="offre_commerce",
            player_only=True,
            conds=(("other_alive",),),
            mood="peuple",
            options=(
                Option("Accepter l'accord", effects=(("pact", "commerce"),), text="Vos villages commerceront avec les {other}.", ai=1.2),
                Option("Refuser", effects=(("relation", -3),), text="Vous renvoyez les porteurs des {other}."),
            ),
        ),
        Event(
            "exige_tribut",
            "Ils exigent un tribut",
            "Les {other}, nombreux et forts, exigent des vivres chaque saison. Sinon, disent-ils, ils "
            "viendront les prendre.",
            trigger="exige_tribut",
            player_only=True,
            conds=(("other_alive",),),
            mood="danger",
            options=(
                Option("Payer", effects=(("pact", "tribut_paye"),), text="Vous paierez les {other} chaque saison.", ai=1.0),
                Option("Refuser", effects=(("casus",),), text="Vous refusez : les {other} viendront peut-être se servir.", ai=0.8),
            ),
        ),
        # --- la fievre --------------------------------------------------------
        Event(
            "fievre",
            "La fièvre",
            "Une fièvre court dans le camp de {band}. Les enfants toussent, les anciens ne se levent plus.",
            conds=(("not_village",), ("season", "ete", "automne"), ("pop_ge", 60)),
            weight=0.03,
            cooldown=78,
            mood="danger",
            options=(
                Option(
                    "Isoler les malades",
                    effects=(("pop_pct", -0.05),),
                    follow=(Follow("fievre_gagne", 0.1, (2, 5), "other_band"),),
                    text="On isole les malades : la fièvre s'éteint lentement.",
                    ai=1.4,
                ),
                Option(
                    "Rites de guérison",
                    outcomes=(
                        Outcome(0.5, (("pop_pct", -0.03), ("prestige", 1)), (), "Les rites ont apaisé la fièvre.", mods=((("knows", "rites"), 0.2),)),
                        Outcome(0.5, (("pop_pct", -0.08),), (Follow("fievre_gagne", 0.3, (2, 5), "other_band"),), "Les rites n'ont rien fait : beaucoup sont morts."),
                    ),
                ),
                Option(
                    "Fuir ce lieu",
                    effects=(("stock", -1), ("goto_far", 6, 12)),
                    follow=(Follow("fievre_gagne", 0.15, (2, 5), "other_band"),),
                    text="{Band} fuit le lieu maudit.",
                ),
            ),
        ),
        Event(
            "fievre_gagne",
            "La fièvre gagne",
            "La fièvre a gagne {band}.",
            trigger="follow",
            mood="danger",
            options=(
                Option("Isoler les malades", effects=(("pop_pct", -0.05),), text="On isole les malades.", ai=1.3),
                Option(
                    "Prier les esprits",
                    outcomes=(
                        Outcome(0.5, (("pop_pct", -0.02),), (), "Les esprits ont écoute."),
                        Outcome(0.5, (("pop_pct", -0.08),), (), "La fièvre a emporte beaucoup de monde."),
                    ),
                ),
            ),
        ),
        # --- l'hiver terrible ----------------------------------------------------
        Event(
            "hiver_rude",
            "Un hiver terrible s'annonce",
            "Les anciens sentent venir un hiver terrible : les oies sont parties tôt, la neige tombe déjà sur les hauteurs.",
            conds=(("not_village",), ("week_between", 36, 43), ("winter_long", 12), ("stock_lt", 10)),
            weight=0.10,
            cooldown=104,
            mood="danger",
            options=(
                Option(
                    "Faire des réserves",
                    effects=(("stop",), ("stock", 3)),
                    text="Chasse, séchage, cueillette : {band} remplit ses réserves.",
                    ai=1.4,
                ),
                Option("Partir vers le soleil", effects=(("goto_warm", 20),), text="{Band} part vers des terres à l'hiver plus court."),
                Option(
                    "Faire confiance aux esprits",
                    follow=(Follow("hiver_frappe", 0.5, (6, 12)),),
                    text="On fait des offrandes, et on attend.",
                    ai=0.4,
                ),
            ),
        ),
        Event(
            "hiver_frappe",
            "Le grand froid",
            "Le froid est tombé d'un coup sur {band}. Les réserves gèlent, le gibier a disparu.",
            trigger="follow",
            mood="danger",
            options=(
                Option("Tenir ensemble", effects=(("stock", -2), ("loyalty_all", 3)), text="On se serre autour du feu.", ai=1.2),
                Option(
                    "Envoyer les jeunes chasser",
                    outcomes=(
                        Outcome(0.5, (("stock", 2),), (), "Les jeunes reviennent avec du gibier.", mods=((("knows", "peaux"), 0.15),)),
                        Outcome(0.5, (("pop", -3, -1),), (), "Certains ne sont jamais revenus."),
                    ),
                ),
            ),
        ),
        # --- la grotte ornee -------------------------------------------------------
        Event(
            "grotte",
            "La grotte ornée",
            "Les chasseurs de {band} ont trouve une grotte profonde. Sur les parois, des bêtes peintes "
            "par des hommes d'avant.",
            conds=(("terrain", "colline", "montagne"),),
            weight=0.015,
            once=True,
            mood="esprit",
            options=(
                Option(
                    "Y peindre nos propres bêtes",
                    effects=(("prestige", 3), ("flag", "grotte")),
                    follow=(Follow("grotte_recits", 0.6, (20, 45)),),
                    text="La paroi porte maintenant vos bêtes à côté de celles des anciens.",
                    ai=1.3,
                ),
                Option("En faire un abri", effects=(("camp",), ("prestige", 1)), text="La grotte devient un abri."),
                Option("La laisser aux esprits", effects=(("loyalty_all", 3),), text="On referme l'entrée avec des pierres."),
            ),
        ),
        Event(
            "grotte_recits",
            "Les récits de la grotte",
            "Chaque hiver, on retourne à la grotte. Les anciens y racontent les chasses d'autrefois.",
            trigger="follow",
            mood="esprit",
            options=(
                Option(
                    "Écouter les anciens",
                    effects=(("tech_progress_id", "conte", 0.35), ("loyalty_all", 2)),
                    text="Les récits relient les clans : les Récits autour du feu avancent.",
                ),
            ),
        ),
        # --- l'etranger blesse ---------------------------------------------------
        Event(
            "blesse",
            "L'étranger blessé",
            "Un homme d'un peuple inconnu a été trouvé près de {band}, blessé, a moitié mort de froid.",
            weight=0.01,
            cooldown=156,
            mood="peuple",
            options=(
                Option(
                    "Le soigner",
                    effects=(("stock", -0.5),),
                    follow=(Follow("gueri", 0.7, (4, 10)),),
                    text="On soigne l'étranger.",
                    ai=1.3,
                ),
                Option("Le laisser à son sort", text="On passe son chemin."),
            ),
        ),
        Event(
            "gueri",
            "L'étranger guéri",
            "L'étranger est guéri. Avant de partir, il dessine dans la terre les chemins de son pays et parle de terres lointaines.",
            trigger="follow",
            mood="chance",
            options=(
                Option("Écouter et retenir", effects=(("reveal", 18),), text="Vous savez maintenant ce qu'il y a {lieu}.", ai=1.2),
                Option("Lui proposer de rester", effects=(("pop", 1, 1), ("loyalty", 2)), text="L'étranger reste parmi vous."),
            ),
        ),
        # --- presages ---------------------------------------------------------------
        Event(
            "presage",
            "L'étoile chevelue",
            "Une étoile chevelue traverse le ciel pendant des nuits. Les enfants n'osent plus sortir.",
            scope="tribe",
            weight=0.008,
            cooldown=260,
            mood="esprit",
            options=(
                Option(
                    "C'est un signe de grandeur",
                    effects=(("prestige", 4),),
                    follow=(Follow("presage_malheur", 0.25, (8, 26)),),
                    text="Le chef l'annonce : l'étoile promet de grandes choses.",
                ),
                Option("Faire des offrandes", effects=(("stock_all", -1), ("loyalty_all", 5)), text="Les offrandes rassurent les clans.", ai=1.2),
            ),
        ),
        Event(
            "presage_malheur",
            "Le mauvais sort",
            "Depuis l'étoile, le malheur s'acharne : la chasse est maigre, on se dispute pour un rien.",
            scope="tribe",
            trigger="follow",
            mood="esprit",
            options=(
                Option("Chercher un coupable", effects=(("loyalty_all", -5), ("prestige", 1)), text="On a chasse un coupable. Le calme revient, mal."),
                Option("Faire de nouvelles offrandes", effects=(("stock_all", -1), ("loyalty_all", 3)), text="Les offrandes apaisent les esprits.", ai=1.3),
            ),
        ),
        # --- caches -----------------------------------------------------------------
        Event(
            "cache_trouvee",
            "Une cache étrangère",
            "Vos chasseurs découvrent une cache de viande séchée des {other}, à peine cachée sous des pierres.",
            trigger="cache_trouvee",
            player_only=True,
            conds=(("site_alive",),),
            cooldown=26,
            deadline=6,
            mood="neutre",
            options=(
                Option(
                    "La prendre",
                    outcomes=(
                        Outcome(0.5, (("steal_cache",), ("relation", -10)), (), "Vous prenez les vivres ({butin}). Les {other} l'ont su."),
                        Outcome(0.5, (("steal_cache",),), (), "Vous prenez les vivres ({butin}). Personne n'a rien vu."),
                    ),
                ),
                Option("La laisser", text="On laisse la cache des {other} où elle est.", ai=1.1),
            ),
        ),
        # --- rassemblements, jeunes qui partent -------------------------------------------
        Event(
            "rassemblement",
            "Le grand rassemblement",
            "Plusieurs clans se retrouvent autour du feu de {chief} pour l'hiver. On chante, on échange, on se marie.",
            conds=(("chief_band",), ("season", "hiver"), ("crowded", 2)),
            weight=0.08,
            cooldown=52,
            mood="chance",
            options=(
                Option(
                    "Grande fête",
                    effects=(("stock_near", -1), ("loyalty_near", 15), ("prestige", 2)),
                    follow=(Follow("fete_mariages", 0.4, (2, 6)),),
                    text="Une fête dont on se souviendra : les clans repartent unis.",
                    ai=1.3,
                ),
                Option("Rester sobres", text="On garde les vivres pour la fin de l'hiver."),
            ),
        ),
        Event(
            "fete_mariages",
            "Des mariages",
            "La fête a noué des liens : des jeunes de clans différents s'unissent.",
            trigger="follow",
            mood="chance",
            options=(Option("Béni soit ce jour", effects=(("pop", 1, 3), ("loyalty_all", 3)), text="Les clans sont plus unis que jamais."),),
        ),
        Event(
            "jeunes_partent",
            "Les jeunes veulent partir",
            "Des jeunes de {band} veulent partir fonder leur propre clan, au-delà des collines.",
            conds=(("season", "printemps"), ("pop_ge", 45), ("can_split",)),
            weight=0.03,
            cooldown=104,
            mood="peuple",
            options=(
                Option("Les laisser partir", effects=(("split",),), text="Un nouveau clan est ne.", ai=1.2),
                Option("Les retenir", effects=(("loyalty", -5),), text="Les jeunes restent, a contrecœur."),
                Option(
                    "Les envoyer explorer au loin",
                    effects=(("split", 20, 30), ("prestige", 1)),
                    text="Le nouveau clan part vers l'inconnu.",
                ),
            ),
        ),
        # --- la vie de tous les jours -------------------------------------------------------
        Event(
            "enfant_prodige",
            "Une idée neuve",
            "Une jeune fille de {band} a une idée que personne n'avait eue. Les anciens hochent la tête, surpris.",
            conds=(("learning",),),
            weight=0.025,
            cooldown=104,
            mood="chance",
            options=(
                Option(
                    "Qu'elle enseigne à tous",
                    effects=(("learn_boost", 0.3),),
                    text="Son idée fait son chemin : {savoir} avance.",
                    ai=1.3,
                ),
                Option(
                    "Qu'elle garde les récits de la tribu",
                    effects=(("prestige", 2), ("loyalty_all", 2)),
                    text="Elle apprend les récits des anciens pour les transmettre.",
                ),
            ),
        ),
        Event(
            "querelle",
            "Une querelle de chasseurs",
            "Les chasseurs de {band} et ceux d'un clan voisin se disputent le même gibier. Les coups ne sont pas loin.",
            conds=(("not_chief_band",), ("crowded", 1)),
            weight=0.03,
            cooldown=52,
            mood="peuple",
            options=(
                Option(
                    "Le chef tranche",
                    effects=(("chief_renown", 3), ("loyalty", -5)),
                    text="{chief} a tranche. Le clan de {leader} obéit, sans joie.",
                ),
                Option(
                    "Partager les terres de chasse",
                    effects=(("loyalty_near", 3), ("stock", -0.5)),
                    text="Chacun aura ses vallées : la paix revient.",
                    ai=1.3,
                ),
                Option(
                    "Les laisser régler ça entre eux",
                    outcomes=(
                        Outcome(0.5, (), (), "La dispute s'éteint d'elle-même."),
                        Outcome(
                            0.5,
                            (("loyalty", -10), ("pop", -2, -1)),
                            (Follow("rivalite", 0.4, (8, 26)),),
                            "La dispute a tourné à la bagarre : il y a des morts.",
                        ),
                    ),
                    ai=0.5,
                ),
            ),
        ),
        Event(
            "visiteurs",
            "Une famille errante",
            "Une petite famille errante demande à rejoindre {band}. Ils ont faim, mais ils savent chasser.",
            weight=0.02,
            cooldown=78,
            mood="peuple",
            options=(
                Option("Les accueillir", effects=(("pop", 4, 7), ("stock", -1)), text="La famille rejoint {band}.", ai=1.3),
                Option("Les renvoyer", text="La famille repart, seule."),
            ),
        ),
        Event(
            "source",
            "La source chaude",
            "Au fond d'une vallée, les enfants de {band} ont trouve une source chaude. La vapeur monte dans l'air froid.",
            conds=(("terrain", "vallee", "foret", "colline"),),
            weight=0.012,
            once=True,
            mood="esprit",
            options=(
                Option("En faire un lieu sacré", effects=(("prestige", 2), ("loyalty_all", 3)), text="La source devient un lieu sacré.", ai=1.2),
                Option("S'y installer pour l'hiver", effects=(("camp",),), text="Un campement près de la source."),
            ),
        ),
        Event(
            "orage",
            "L'orage",
            "Un orage terrible a frappe {band} : la foudre a mis le feu aux herbes sèches, le vent pousse les flammes vers le camp.",
            conds=(("not_village",), ("season", "ete"), ("terrain", "plaine", "steppe", "foret")),
            weight=0.03,
            cooldown=104,
            mood="danger",
            options=(
                Option("Fuir devant le feu", effects=(("goto_far", 5, 9), ("stock", -1)), text="{Band} fuit devant les flammes.", ai=1.2),
                Option(
                    "Sauver les réserves",
                    outcomes=(
                        Outcome(0.6, (("stock", -1),), (), "On a sauve l'essentiel."),
                        Outcome(0.4, (("stock", -3), ("pop", -2, -1)), (), "Le feu a tout pris, et des gens avec."),
                    ),
                ),
            ),
        ),
        Event(
            "ancien",
            "Le dernier des anciens",
            "Le plus vieux de la tribu, le dernier a se souvenir des grands hivers, sent venir sa fin.",
            scope="tribe",
            conds=(("bands_ge", 2),),
            weight=0.015,
            cooldown=260,
            mood="esprit",
            options=(
                Option(
                    "Recueillir ses récits",
                    effects=(("tech_progress_id", "conte", 0.3), ("prestige", 1)),
                    text="Ses récits ne seront pas perdus.",
                    ai=1.2,
                ),
                Option(
                    "Lui offrir de grandes funérailles",
                    effects=(("stock_all", -0.5), ("loyalty_all", 5)),
                    text="Tous les clans viennent l'honorer.",
                ),
            ),
        ),
        # --- villages -------------------------------------------------------------------
        Event(
            "crue",
            "La crue",
            "La rivière est sortie de son lit : l'eau monte dans les champs et jusqu'aux maisons de {band}.",
            trigger="crue",
            conds=(("village",),),
            mood="danger",
            deadline=6,
            options=(
                Option("Sauver le grenier", effects=(("seed_pct", -0.5), ("burn",)), text="Le grain est sauve, mais la moitié des semences est perdue.", ai=1.0),
                Option("Sauver les semences", effects=(("stock_pct", -0.3), ("burn",)), text="Les semences sont à l'abri ; le grenier a souffert.", ai=1.2),
                Option(
                    "Monter sur les hauteurs et attendre",
                    outcomes=(
                        Outcome(0.5, (("stock_pct", -0.1),), (), "L'eau est redescendue vite : peu de dégâts."),
                        Outcome(0.5, (("stock_pct", -0.3), ("seed_pct", -0.5), ("burn",)), (), "La crue a tout emporte."),
                    ),
                    ai=0.6,
                ),
            ),
        ),
        Event(
            "semences",
            "Manger les semences ?",
            "La faim ronge {band}. Il reste les semences de l'an prochain, dans les jarres du fond du grenier.",
            trigger="semences",
            conds=(("village",),),
            mood="danger",
            deadline=4,
            options=(
                Option("Garder les semences", text="On serre les dents : les semences attendront le printemps.", ai=1.2),
                Option("Manger les semences", effects=(("eat_seed",),), text="On mange les semences ({butin}) : pas de champs au printemps."),
            ),
        ),
        Event(
            "fievre_village",
            "La fièvre au village",
            "Trop de monde, trop près : une fièvre court de maison en maison à {band}.",
            trigger="fievre_village",
            conds=(("village",),),
            mood="danger",
            options=(
                Option("Isoler les maisons malades", effects=(("pop_pct", -0.04),), text="On isole les malades : la fièvre recule.", ai=1.3),
                Option(
                    "Rites de guérison",
                    outcomes=(
                        Outcome(0.5, (("pop_pct", -0.03), ("prestige", 1)), (), "Les rites ont apaisé la fièvre.", mods=((("knows", "ancetres"), 0.15), (("knows", "rites"), 0.1))),
                        Outcome(0.5, (("pop_pct", -0.10),), (), "La fièvre a emporte beaucoup de monde."),
                    ),
                ),
                Option(
                    "Envoyer une partie du village camper au loin",
                    effects=(("split", 8, 14), ("pop_pct", -0.02)),
                    requires=(("can_split",),),
                    text="Une partie du village part vivre à l'air libre.",
                ),
            ),
        ),
        Event(
            "bonne_recolte",
            "Une récolte magnifique",
            "Les épis sont lourds, les greniers débordent : jamais {band} n'a vu pareille récolte.",
            trigger="bonne_recolte",
            conds=(("village",),),
            mood="chance",
            options=(
                Option("Grande fête des moissons", effects=(("stock", -1), ("loyalty_all", 6), ("prestige", 2)), text="La fête des moissons unit toute la tribu.", ai=1.2),
                Option("Tout garder au grenier", text="Le grain est serre dans les greniers."),
            ),
        ),
        Event(
            "colporteurs",
            "Des colporteurs",
            "Des colporteurs venus de loin, leurs paniers sur le dos, s'arrêtent à {band} : du sel, des "
            "haches de pierre polie, qu'ils échangent contre du grain.",
            conds=(("village",), ("no_trade",), ("stock_ge", 8)),
            weight=0.03,
            cooldown=104,
            mood="peuple",
            options=(
                Option("Du sel contre du grain", effects=(("stock", -0.6), ("good", "sel", 8)), text="Les jarres de sel s'alignent au grenier.", ai=1.0),
                Option("Des haches contre du grain", effects=(("stock", -0.6), ("good", "haches", 8)), text="Les haches polies passent de main en main.", ai=0.9),
                Option("Les renvoyer", text="Les colporteurs reprennent la route."),
            ),
        ),
        Event(
            "porteurs_perdus",
            "Des porteurs disparus",
            "Les porteurs de la route des {other} ne sont pas revenus. Des pillards ? Le gué en crue ? "
            "À {band}, on attend des nouvelles.",
            conds=(("village",), ("trade_partner",)),
            weight=0.02,
            cooldown=78,
            mood="danger",
            options=(
                Option(
                    "Envoyer des hommes à leur recherche",
                    outcomes=(
                        Outcome(0.6, (("stock", -0.2), ("relation", 6), ("prestige", 1)), (), "On les retrouve, blessés mais vivants : les {other} ne l'oublieront pas."),
                        Outcome(0.4, (("stock", -0.2), ("lose_goods", 4)), (), "On ne retrouve que des paniers éventrés."),
                    ),
                    ai=1.1,
                ),
                Option("Les pleurer et continuer", effects=(("lose_goods", 6),), text="La charge est perdue ; la route reprendra.", ai=0.9),
            ),
        ),
        Event(
            "marchand_lointain",
            "Un marchand venu de loin",
            "Arrive avec les porteurs des {other}, un homme d'un pays lointain étale des coquillages et des "
            "perles d'ambre devant {band}. Il raconte les terres qu'il a traversées.",
            conds=(("village",), ("trade_partner",)),
            weight=0.02,
            cooldown=104,
            mood="peuple",
            options=(
                Option("Troquer du grain contre ses parures", effects=(("stock", -0.5), ("prestige", 3)), text="Les parures brillent au cou des anciens.", ai=1.0),
                Option("L'écouter raconter le chemin", effects=(("reveal", 12),), text="On dessine sur le sable les pays qu'il a vus.", ai=0.8),
                Option("Lui offrir l'hospitalité", effects=(("relation", 4), ("prestige", 1)), text="Les {other} apprendront comment vous recevez.", ai=1.0),
            ),
        ),
        Event(
            "belle_veine",
            "Une belle veine",
            "Les gens de métier de {band} ont trouve une veine d'une qualité rare. On en parle jusque chez les voisins.",
            conds=(("village",), ("crafts",)),
            weight=0.03,
            cooldown=104,
            mood="chance",
            options=(
                Option("Travailler jour et nuit", effects=(("craft_bonus", 10),), text="Les réserves se remplissent.", ai=1.1),
                Option("Montrer l'ouvrage à tous", effects=(("prestige", 3),), text="On vient de loin admirer l'ouvrage de {band}.", ai=0.9),
            ),
        ),
        Event(
            "nomades",
            "Des nomades rodent",
            "Des bandes des {other} rodent autour des champs de {band}. Ils regardent les greniers.",
            conds=(("village",), ("foreign_near", 12)),
            weight=0.05,
            cooldown=52,
            mood="danger",
            options=(
                Option(
                    "Leur offrir une part de la récolte",
                    effects=(("stock", -1.5), ("relation", 12)),
                    text="Les {other} emportent leur part et s'éloignent.",
                    ai=1.1,
                ),
                Option("Monter la garde", effects=(("flag", "sur_gardes", 8),), text="On veille jour et nuit sur les greniers.", ai=1.2),
                Option("Les chasser", effects=(("relation", -15), ("provoke",)), text="On chasse les {other} a coups de pierres.", ai=0.4),
            ),
        ),
        # --- succession ------------------------------------------------------------------
        Event(
            "succession",
            "Qui mènera la tribu ?",
            "{dead}, votre chef, est mort {cause}. Les clans se réunissent autour du feu : qui mènera la tribu ?",
            scope="tribe",
            trigger="succession",
            player_only=True,
            mood="esprit",
            deadline=8,
            special="succession",
        ),
        Event(
            "succession_contestee",
            "Un chef conteste",
            "{leader} ne reconnaît pas {chief} comme chef. Son clan attend de voir qui cédera.",
            trigger="follow",
            conds=(("not_chief_band",),),
            mood="danger",
            options=(
                Option(
                    "Faire des concessions",
                    effects=(("prestige", -5), ("loyalty", 20)),
                    requires=(("prestige_ge", 5),),
                    text="Des concessions ramenent {leader} dans le rang.",
                    ai=1.2,
                ),
                Option(
                    "Le défier",
                    outcomes=(
                        Outcome(0.5, (("loyalty", 10), ("chief_renown", 10)), (), "{chief} l'a emporte : {leader} se soumet.", mods=((("chief_stronger",), 0.2),)),
                        Outcome(0.5, (("loyalty", -30),), (Follow("clan_part", 0.6, (2, 8)),), "{leader} a tenu tête : son clan veut partir."),
                    ),
                ),
                Option("L'ignorer", effects=(("loyalty", -20),), text="On fait comme si de rien n'était."),
            ),
        ),
    )
}
