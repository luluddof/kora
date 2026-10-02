"""Le francais avec ses accents (charte graphique, section 3).

convert(texte) remet les accents d'un texte ecrit sans : un dictionnaire de
mots sans ambiguite (MOTS), des tournures pour les mots a double sens
(PHRASES : cote/côté, ou/où...), la regle du « à », puis des corrections
(APRES). tools/accents.py s'en est servi pour les textes du code ; la
sauvegarde s'en sert pour les journaux des anciennes parties.
"""

import re

MOTS = """
abandonne=abandonné abandonnee=abandonnée achete=acheté achetent=achètent achevee=achevée affichee=affichée
affames=affamés age=âge agite=agité aiguise=aiguisé alle=allé allie=allié allies=alliés ancetres=ancêtres
aneantie=anéantie aneantis=anéantis annee=année annees=années apaise=apaisé apercu=aperçu apercus=aperçus
apparait=apparaît apprivoise=apprivoisé armee=armée armees=armées arriere=arrière attaques=attaqués
bati=bâti batiment=bâtiment batiments=bâtiments batir=bâtir batisseurs=bâtisseurs beni=béni betes=bêtes
blesse=blessé blesses=blessés boeufs=bœufs brule=brûle brules=brûlés ca=ça cachee=cachée cedera=cédera
celebre=célèbre celebrer=célébrer celebres=célèbres cereales=céréales chevres=chèvres coeur=cœur
contrecoeur=contrecœur comparees=comparées complete=complète confederation=confédération connait=connaît
connaitre=connaître coute=coûte coutent=coûtent creation=création croit=croît croutes=croûtes
debordent=débordent debrouilleront=débrouilleront debut=début decide=décidé decider=décider decidera=décidera
declinez=déclinez decouverte=découverte decouvrent=découvrent decus=déçus defaire=défaire defend=défend
defense=défense defenseur=défenseur defier=défier defricher=défricher degats=dégâts deja=déjà dela=delà
depart=départ deplacer=déplacer deposer=déposer derniere=dernière dernieres=dernières deroute=déroute
desert=désert desertent=désertent desherbe=désherbe designe=désigné designer=désigner desordre=désordre
desormais=désormais detache=détache detacher=détacher detail=détail detroits=détroits detruite=détruite
differentes=différentes differents=différents dispersee=dispersée divisees=divisées dompte=dompté dores=dorés
dressee=dressée dressees=dressées duree=durée ecartee=écartée echange=échange echangent=échangent
echanger=échanger echangeront=échangeront echanges=échanges echap=échap echappe=échappe echappee=échappée
eclaireurs=éclaireurs ecoute=écoute ecouter=écouter ecran=écran ecrire=écrire ecrivez=écrivez effacee=effacée
eleve=élève emportes=emportés encercles=encerclés enterres=enterrés entree=entrée envoyes=envoyés
epaules=épaules epieu=épieu epieux=épieux epis=épis epousent=épousent epuise=épuisé epuisees=épuisées
epuisement=épuisement epuisent=épuisent equipe=équipe equipes=équipes etabli=établi etale=étale
etalent=étalent ete=été etendue=étendue etes=êtes etoffes=étoffes etoile=étoile etrange=étrange
etranger=étranger etrangere=étrangère etrangers=étrangers etre=être evenement=événement eventres=éventrés
fache=fâché fecond=fécond fermee=fermée fertilite=fertilité fete=fête fidele=fidèle fievre=fièvre
fievres=fièvres filee=filée fleches=flèches foret=forêt forets=forêts fumee=fumée fumes=fumés freres=frères
funerailles=funérailles gate=gâte gatent=gâtent gelent=gèlent genereux=généreux gerer=gérer gue=gué
guere=guère gueri=guéri guerison=guérison hebergee=hébergée heberger=héberger heritier=héritier
honore=honoré hote=hôte humidite=humidité idee=idée independance=indépendance interieure=intérieure
isole=isolé jachere=jachère jalonnes=jalonnés lancees=lancées legendaire=légendaire levee=levée
levees=levées libere=libéré liberer=libérer lisiere=lisière lumiere=lumière maitriser=maîtriser marie=marié
massacres=massacrés mefiants=méfiants melee=mêlée meme=même memes=mêmes mene=mène menera=mènera
menerait=mènerait menes=menés metier=métier metiers=métiers moitie=moitié neolithique=néolithique nes=nés
noue=noué obeiront=obéiront obeit=obéit ocean=océan ornee=ornée oublie=oublié pale=pâle partagee=partagée
peche=pêche pecheurs=pêcheurs percants=perçants pieges=pièges pille=pillé pillee=pillée prepare=prépare
preparer=préparer pres=près present=présent presents=présents pret=prêt prets=prêts prevoyants=prévoyants
prive=privé premiere=première premieres=premières prosperes=prospères qualite=qualité reussi=réussi
reussissent=réussissent rase=rasé recemment=récemment recent=récent recente=récente recents=récents
recits=récits recolte=récolte recoltes=récoltes reconnait=reconnaît recopiee=recopiée recue=reçue recus=reçus
redoutes=redoutés reequipe=rééquipe reequiper=rééquiper refusee=refusée regler=régler reguliers=réguliers
renomme=renommé renommee=renommée rentree=rentrée reperes=repères repondu=répondu reponse=réponse
reputation=réputation reseau=réseau reserve=réserve reserves=réserves reuni=réuni reunies=réunies
reunir=réunir reunissent=réunissent riviere=rivière role=rôle arrete=arrête arretent=arrêtent
eloigne=éloigne eloignent=éloignent emancipent=émancipent emanciperont=émanciperont etait=était
eteignent=éteignent eteint=éteint etendre=étendre sacre=sacré salee=salée sante=santé
sauvegardee=sauvegardée scellee=scellée sechage=séchage sechee=séchée seches=sèches seche=sèche
separation=séparation sepultures=sépultures societe=société stabilite=stabilité succede=succède
succedera=succédera sureleve=surélevé sureleves=surélevés tannees=tannées tete=tête termine=terminé
tirees=tirées tissee=tissée tisses=tissés tot=tôt traineaux=traîneaux traitre=traître traitres=traîtres
traversees=traversées tres=très tresses=tressés treve=trêve unite=unité unites=unités vallee=vallée
vallees=vallées vecu=vécu vecues=vécues verifiez=vérifiez verrouille=verrouillé vetements=vêtements
voila=voilà portee=portée accepte=accepté hiver=hiver epineux=épineux oeuvre=œuvre hospitalite=hospitalité elan=élan
arrivee=arrivée deposer=déposer decouvert=découvert eleves=élevés eleveurs=éleveurs ecoutent=écoutent
evenements=événements etat=état etats=états equilibre=équilibre periode=période region=région
regions=régions numero=numéro general=général generale=générale precedent=précédent prochaines=prochaines
""".split()
MOTS = dict(item.split("=", 1) for item in MOTS)
# Tournures : (motif sur mots ASCII, remplacement), avant le dictionnaire.
PHRASES = [
    (r"\bmise de cote\b", "mise de côté"), (r"\bmises de cote\b", "mises de côté"), (r"\bde leur cote\b", "de leur côté"),
    (r"\bd'un cote\b", "d'un côté"), (r"\bde l'autre cote\b", "de l'autre côté"), (r"\ba cote de\b", "à côté de"),
    (r"\bcote a cote\b", "côte à côte"), (r"\bde cote\b", "de côté"), (r"\b([Cc])ote\b", r"\1ôte"),
    (r"\bbon marche\b", "bon marché"), (r"\bMARCHE DU\b", "MARCHÉ DU"), (r"\bdes deux marches\b", "des deux marchés"),
    (r"\bPoisson seche\b", "Poisson séché"), (r"\bpoisson seche\b", "poisson séché"),
    (r"\bou l'on\b", "où l'on"), (r"\bLa ou\b", "Là où"), (r"\bla ou\b", "là où"), (r"\bd'ou\b", "d'où"),
    (r"\bD'ou\b", "D'où"), (r"\bpar ou\b", "par où"), (r"\bou elle est\b", "où elle est"), (r"\bet ou les\b", "et où les"),
    (r"\bplace ou les\b", "place où les"), (r"\babris ou potiers\b", "abris où potiers"), (r"\bjusqu'ou\b", "jusqu'où"),
    (r"\b([Dd])es (le|la|les|que|qu')\b", r"\1ès \2"), (r"\bvous etes\b", "vous êtes"), (r"\bVous etes\b", "Vous êtes"),
    (r"\bPeuple fixe\b", "Peuple fixé"), (r"\bpeuple fixe\b", "peuple fixé"), (r"\bpeuples fixes\b", "peuples fixés"),
    (r"\bdecide d'office\b", "décidé d'office"), (r"\bDecide d'office\b", "Décidé d'office"),
    (r"\b(avez|ai|a|ont|avons) (deja|déjà) propose\b", r"\1 déjà proposé"), (r"\bramene a\b", "ramené à"),
    (r"\by a \{", "y a {"),
]
# « a » devient « à » devant ces mots (article, nombre, possessif...) ou
# apres ces mots (jusqu', grace, face...) ; devant un infinitif aussi.
A_AVANT = set("""la l' l un une deux trois quatre cinq six sept huit neuf dix chaque son sa ses leur leurs vos votre nos notre
ce cet cette ces moins peu pied portee portée cote côté mi chacun chacune quelques plusieurs eux elle lui toi moi nous vous
tous toutes droite gauche l'est l'ouest l'abri l'aube terre bord peine part vie jamais nouveau temps
""".split())
A_APRES = set("jusqu grace grâce face quant pret prêt prets prêts prete prête apte".split())
A_VERBE = set("y il elle on qui ce cela ça ca chacun personne rien".split())
# Apres coup : les « à » qui etaient des verbes.
APRES = [
    (r"\bpeuple à son\b", "peuple a son"),
    (r"\bà une idée\b", "a une idée"), (r"\bà un nom\b", "a un nom"), (r"\bclan à son chef\b", "clan a son chef"),
    (r"\bà tout emporte\b", "a tout emporté"), (r"\bà tout pris\b", "a tout pris"), (r"\ba tourne\b", "a tourné"),
    (r"([lL]\\?')honoré\b", r"\1honore"),
    (r"\b([Oo])n isolé", r"\1n isole"), (r"\bRentrer libéré", "Rentrer libère"), (r"\bse marié\b", "se marie"),
    (r"\bmène par\b", "mené par"), (r"\b(s\\?')épuisé", r"\1épuise"), (r"\best tombe\b", "est tombé"),
    (r"\bété trouve\b", "été trouvé"),
]
NOT_INF = set("pierre guerre terre frere frère autre notre votre leur hiver lever premier dernier cuir peur".split())
WORD = re.compile(r"[A-Za-zÀ-ÿœŒ]+")


def case_like(src: str, dst: str) -> str:
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[0].isupper():
        return dst[0].upper() + dst[1:]
    return dst


def convert(text: str, after: str = "") -> str:
    """after : ce qui suit le morceau dans le code (le « { » d'une f-string)."""
    for pat, rep in PHRASES:
        text = re.sub(pat, rep, text)
    # Les mots.
    out = []
    pos = 0
    words = list(WORD.finditer(text))
    for i, m in enumerate(words):
        w = m.group(0)
        out.append(text[pos:m.start()])
        low = w.lower()
        new = w
        # Pas apres une barre oblique inverse (\n, \t) : ce n'est pas un mot.
        if m.start() > 0 and text[m.start() - 1] == "\\":
            new = w
        elif low in MOTS:
            new = case_like(w, MOTS[low])
        elif w in ("a", "A"):
            prev = words[i - 1].group(0).lower() if i > 0 else ""
            nxt = words[i + 1].group(0).lower() if i + 1 < len(words) else ""
            between = text[m.end():words[i + 1].start()] if i + 1 < len(words) else ""
            nxt_full = (nxt + "'") if between.startswith("'") else nxt
            gap_prev = text[words[i - 1].end():m.start()] if i > 0 else ""
            num = re.match(r"\s*[\d{]", text[m.end():] + after)
            if prev in A_VERBE:
                new = w
            elif w == "A" and (i == 0 or gap_prev.strip().endswith((".", ":", "!", "?", "·", "("))):
                # En tete de phrase, « A » est presque toujours la preposition.
                new = "À"
            elif prev in A_APRES and gap_prev in ("'", "' "):
                new = "à"
            elif nxt in A_AVANT or nxt_full in A_AVANT or num:
                new = "à"
            elif len(nxt) > 3 and nxt.endswith(("er", "ir", "re")) and nxt not in NOT_INF and between == " ":
                new = "à"
        out.append(new)
        pos = m.end()
    out.append(text[pos:])
    text = "".join(out)
    for pat, rep in APRES:
        text = re.sub(pat, rep, text)
    return text


def needs(text: str) -> bool:
    """Un texte d'avant les accents (que de l'ASCII)."""
    return text.isascii()
