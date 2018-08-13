# -*- coding: utf-8 -*-
# 
# Archéo Lex – Pure Histoire de la Loi française
# – crée un dépôt Git des lois françaises écrites en syntaxe Markdown
# – ce module assemble les textes et fait l’export final
# 
# This program is free software. It comes without any warranty, to
# the extent permitted by applicable law. You can redistribute it
# and/or modify it under the terms of the Do What The Fuck You Want
# To Public License, Version 2, as published by Sam Hocevar. See
# the LICENSE file for more details.

# Imports
import os
import subprocess
import datetime
import time
import re
from multiprocessing import Pool
from pytz import timezone
import legi.utils
from marcheolex import logger
from marcheolex import version_archeolex
from marcheolex import natures
from marcheolex.utilitaires import MOIS
from marcheolex.utilitaires import MOIS2
from marcheolex.utilitaires import comp_infini_strict
from marcheolex.exports import *
from marcheolex.FabriqueArticle import FabriqueArticle
from marcheolex.FabriqueSection import FabriqueSection


def creer_historique_legi(textes, format, dossier, bdd, production):

    if os.path.exists( textes ):
        f_textes = open( textes, 'r' )
        textes = f_textes.read()
        f_textes.close()

    if not os.path.exists( bdd ):
        raise Exception( 'Base de données legi.py manquante.' )

    textes = textes.strip()
    textes = re.split( r'[\n,]+', textes )

    liste_textes = []
    natures = []
    db = legi.utils.connect_db(bdd)
    if 'tout' in textes:
        liste_textes = db.all("""
              SELECT cid
              FROM textes_versions
              ORDER BY cid
        """)
        liste_textes = [ x[0] for x in liste_textes ]
        print( '\nListe de textes : tous\n' )
    elif 'tout-obsolete' in textes:
        last_update = db.one("""
            SELECT value
            FROM db_meta
            WHERE key = 'last_update'
        """)
        liste_textes = db.all("""
              SELECT cid
              FROM textes_versions
              WHERE mtime > {0}
              ORDER BY cid
        """.format(last_update))
        liste_textes = [ x[0] for x in liste_textes ]
    else:
        for texte in textes:
            if re.match( r'^(JORF|LEGI)TEXT[0-9]{12}$', texte ):
                liste_textes.append( texte )
            elif re.match( r'^aleatoire-([0-9]+)$', texte ):
                m = re.match( r'^aleatoire-([0-9]+)$', texte )
                m = int( m.group(1) )
                liste = db.all("""
                      SELECT cid
                      FROM textes_versions
                      ORDER BY RANDOM()
                      LIMIT {0}
                """.format(m))
                liste = [ x[0] for x in liste ]
                liste_textes.extend( liste )
            else:
                if len( natures ) == 0:
                    liste = db.all( """
                          SELECT DISTINCT nature
                          FROM textes_versions
                    """ )
                    natures = [ x[0] for x in liste ]
                if texte.upper() in natures:
                    liste = db.all( """
                          SELECT cid
                          FROM textes_versions
                          WHERE nature = '{0}'
                    """.format( texte.upper() ) )
                    liste = [ x[0] for x in liste ]
                    liste_textes.extend( liste )
                else:
                    raise Exception( 'Mauvaise spécification de la liste de textes' )

    liste_textes.sort()
    if len( liste_textes ) < 100:
        print( '\nListe de textes :\n' + '\n'.join( liste_textes ) + '\n' )

    args = [(texte, format, dossier, bdd) for texte in liste_textes]
    if len(liste_textes) == 1 or os.cpu_count() == 1 or not production:
        textes_traites = list(map(creer_historique_texte, args))
    else:
        nb_procs = min( len(liste_textes), os.cpu_count() )
        textes_traites = list(Pool(nb_procs).map(creer_historique_texte, args))

    return textes_traites


def creer_historique_texte(arg):

    texte, format, dossier, bdd = arg

    logger.info( '> Texte {0}'.format( texte ) )

    # Constantes
    paris = timezone( 'Europe/Paris' )

    # Connexion à la base de données
    db = legi.utils.connect_db(bdd)

    # Créer le dossier si besoin
    sousdossier = '.'
    id = texte
    nom = texte

    # Flags: 1) s’il y a des versions en vigueur future, 2) si la première version est une vigueur future
    futur = False
    futur_debut = False

    # Obtenir la date de la base LEGI
    last_update = db.one("""
        SELECT value
        FROM db_meta
        WHERE key = 'last_update'
    """)
    last_update_jour = datetime.date(*(time.strptime(last_update, '%Y%m%d-%H%M%S')[0:3]))
    last_update = paris.localize( datetime.datetime(*(time.strptime(last_update, '%Y%m%d-%H%M%S')[0:6])) )
    logger.info('Dernière mise à jour de la base LEGI : {}'.format(last_update.isoformat()))

    os.makedirs(dossier, exist_ok=True)
    entree_texte = db.one("""
        SELECT id, nature, titre, titrefull, etat, date_debut, date_fin, num, visas, signataires, tp, nota, abro, rect, cid, mtime
        FROM textes_versions
        WHERE id = '{0}'
    """.format(id))
    if entree_texte == None:
        entree_texte = db.one("""
            SELECT id, nature, titre, titrefull, etat, date_debut, date_fin, num, visas, signataires, tp, nota, abro, rect, cid, mtime
            FROM textes_versions
            WHERE cid = '{0}'
        """.format(id))
    if entree_texte == None:
        raise Exception('Pas de texte avec cet ID ou CID')

    nature = entree_texte[1]
    visas = entree_texte[8] or ''
    signataires = entree_texte[9] or ''
    tp = entree_texte[10] or ''
    nota = entree_texte[11] or ''
    abro = entree_texte[12] or ''
    rect = entree_texte[13] or ''
    cid = entree_texte[14]
    mtime = entree_texte[15]

    visas = visas.strip()
    signataires = signataires.strip()
    tp = tp.strip()
    nota = nota.strip()
    abro = abro.strip()
    rect = rect.strip()

    nature_min = nature.lower()
    nature_min_pluriel = re.sub( r'([- ])', r's\1', nature_min ) + 's'
    if nature in natures.keys():
        nature_min = natures[nature]
        nature_min_pluriel = re.sub( r'([- ])', r's\1', nature_min ) + 's'
        os.makedirs(os.path.join(dossier, nature_min_pluriel), exist_ok=True)
        sousdossier = nature_min_pluriel

    mise_a_jour = True
    if nature and (nature in natures.keys()) and entree_texte[7]:
        identifiant = nature_min+' '+entree_texte[7]
        identifiant = identifiant.replace(' ','_')
        nom_fichier = identifiant
        sousdossier = os.path.join(nature_min_pluriel, identifiant)
        if not os.path.exists(os.path.join(dossier, sousdossier)):
            mise_a_jour = False
        os.makedirs(os.path.join(dossier, sousdossier), exist_ok=True)
    elif nature and (nature in natures.keys()) and entree_texte[2]:
        identifiant = entree_texte[2][0].lower()+entree_texte[2][1:].replace(' ','_')
        nom_fichier = identifiant
        sousdossier = os.path.join(nature_min_pluriel, identifiant)
        if not os.path.exists(os.path.join(dossier, sousdossier)):
            mise_a_jour = False
        os.makedirs(os.path.join(dossier, sousdossier), exist_ok=True)
    else:
        raise Exception('Type bizarre ou inexistant')
        sousdossier = os.path.join(sousdossier, nom)
        nom_fichier = id
    dossier = os.path.join(dossier, sousdossier)
    dossier_final = sousdossier
    nom_final = identifiant
    sousdossier = '.'
    os.makedirs(dossier, exist_ok=True)
    fichier = os.path.join(dossier, nom_fichier + '.md')

    # Créer le dépôt Git avec comme branche maîtresse 'texte' ou 'articles'
    branche = 'texte'
    if format['organisation'] == 'repertoires-simple':
        branche = 'articles'
    if not os.path.exists(os.path.join(dossier, '.git')):
        subprocess.call(['git', 'init'], cwd=dossier)
        subprocess.call(['git', 'symbolic-ref', 'HEAD', 'refs/heads/'+branche], cwd=dossier)
    else:
        subprocess.call(['git', 'checkout', '--', sousdossier], cwd=dossier)
    
    date_reprise_git = None
    reset_hash = ''
    if mise_a_jour:
        tags = subprocess.check_output(['git', 'tag', '-l'], cwd=dossier)
        tags = tags.strip().split('\n')
        date_maj_git = False
        if len(tags) == 0:
            raise Exception('Pas de tag de la dernière mise à jour')
        date_maj_git = paris.localize( datetime.datetime(*(time.strptime(tags[-1], '%Y%m%d-%H%M%S')[0:6])) )
        logger.info('Dernière mise à jour du dépôt : {}'.format(date_maj_git.isoformat()))
        if int(time.mktime(date_maj_git.timetuple())) >= mtime:
            logger.info( 'Dossier : {0}'.format(dossier) )
            logger.info('Pas de mise à jour disponible')
            return

        # Obtention de la première date qu’il faudra mettre à jour
        date_reprise_git = db.one("""
            SELECT date_debut
            FROM articles
            WHERE cid = '{0}' AND mtime > {1}
        """.format(cid,int(time.mktime(date_maj_git.timetuple()))))

        # Lecture des versions en vigueur dans le dépôt Git
        try:
            if subprocess.check_output(['git', 'rev-parse', '--verify', 'futur-'+branche], cwd=dossier):
                subprocess.call(['git', 'checkout', 'futur-'+branche], cwd=dossier)
        except subprocess.CalledProcessError:
            pass
        versions_git = subprocess.check_output(['git', 'log', '--oneline'], cwd=dossier).strip().split('\n')
        for log_version in versions_git:
            for m, k in MOIS.items():
                log_version = log_version.replace( m, k )
            m = re.match(r'^([0-9a-f]+) .* ([0-9]+)(?:er)? ([0-9]+) ([0-9]+)$', log_version)
            if not m:
                raise Exception('Version non reconnue dans le dépôt Git')
            date = '{0:04d}-{1:02d}-{2:02d}'.format(int(m.group(4)), int(m.group(3)), int(m.group(2)))
            reset_hash = m.group(1)
            if date < date_reprise_git:
                break
            reset_hash = ''

        if reset_hash:
            if date_reprise_git <= last_update_jour.strftime('%Y-%m-%d'):
                subprocess.call(['git', 'checkout', branche], cwd=dossier)
                try:
                    if subprocess.check_output(['git', 'rev-parse', '--verify', 'futur-'+branche], cwd=dossier):
                        subprocess.call(['git', 'branch', '-D', 'futur-'+branche], cwd=dossier)
                except subprocess.CalledProcessError:
                    pass
            subprocess.call(['git', 'reset', '--hard', reset_hash], cwd=dossier) 
        else:
            subprocess.call(['git', 'branch', '-m', 'texte', 'junk'], cwd=dossier)
            subprocess.call(['git', 'checkout', '--orphan', branche], cwd=dossier)
            subprocess.call(['git', 'branch', '-D', 'junk'], cwd=dossier)

    # Sélection des versions du texte
    versions_texte_db = db.all("""
          SELECT DISTINCT debut, fin
          FROM sommaires
          WHERE cid = '{0}'
            AND debut < fin
          ORDER BY debut
    """.format(cid))
    dates_texte = []
    dates_fin_texte = []
    versions_texte = []
    for vers in versions_texte_db:
        vt = vers[0]
        if isinstance(vt, str):
            vt = datetime.date(*(time.strptime(vt, '%Y-%m-%d')[0:3]))
        if date_reprise_git and vt.strftime('%Y-%m-%d') < date_reprise_git:
            continue
        dates_texte.append( vt )
        vt = vers[1]
        if isinstance(vt, str):
            vt = datetime.date(*(time.strptime(vt, '%Y-%m-%d')[0:3]))
        dates_fin_texte.append( vt )
    versions_texte = sorted(set(dates_texte).union(set(dates_fin_texte)))
    
    versions_texte = sorted(list(set(versions_texte)))

    syntaxe = Markdown()
    if format['organisation'] == 'repertoires-simple':
        un_article_par_fichier_sans_hierarchie = UnArticleParFichierSansHierarchie('md')
        stockage = StockageGitFichiers(dossier, un_article_par_fichier_sans_hierarchie)
    else:
        fichier_unique = FichierUnique('md')
        stockage = StockageGitFichiers(dossier, fichier_unique)
    fa = FabriqueArticle( db, stockage, syntaxe, True )
    fs = FabriqueSection( fa )

    # Conversion en syntaxe des en-têtes et pied-de-texte
    if visas:
        visas = fs.syntaxe.transformer_depuis_html( visas )
    if signataires:
        signataires = fs.syntaxe.transformer_depuis_html( signataires )
    if tp:
        tp = fs.syntaxe.transformer_depuis_html( tp )
    if nota:
        nota = fs.syntaxe.transformer_depuis_html( nota )

    # Pour chaque version
    # - rechercher les sections et articles associés
    # - créer le fichier texte au format demandé
    # - commiter le fichier
    wnbver = str(len(str(len(versions_texte))))
    erreur_version = False
    for (i_version, version_texte) in enumerate(versions_texte):
        
        # Passer les versions 'nulles'
        #if version_texte.base is None:
        #    continue
        if i_version >= len(versions_texte)-1:
            break

        debut = versions_texte[i_version]
        fin = versions_texte[i_version+1]
        debut_datetime = paris.localize( datetime.datetime( debut.year, debut.month, debut.day ) )

        if not futur and debut > last_update_jour:
            if i_version == 0:
                subprocess.call(['git', 'symbolic-ref', 'HEAD', 'refs/heads/futur-'+branche], cwd=dossier)
                if not reset_hash:
                    futur_debut = True
            else:
                subprocess.call(['git', 'checkout', '-b', 'futur-'+branche], cwd=dossier)
            futur = True

        # Créer l’en-tête
        date_fr = '{} {} {}'.format(debut.day, MOIS2[int(debut.month)], debut.year)
        if debut.day == 1:
            date_fr = '1er {} {}'.format(MOIS2[int(debut.month)], debut.year)
        contenu = nom + '\n'   \
                  + '\n'   \
                  + '- Date de consolidation : ' + date_fr + '\n'            \
                  + '- [Lien permanent Légifrance](https://www.legifrance.gouv.fr/affichCode.do?cidTexte=' + cid + '&dateTexte=' + debut.isoformat().replace('-','') + ')\n' \
                  + '\n' \
                  + '\n'

        # Retrait des fichiers des anciennes versions
        if format['organisation'] != 'fichier-unique':
            subprocess.call('rm -f *.md', cwd=dossier, shell=True)

        # Créer les sections (donc tout le texte)
        contenu, fin_vigueur = fs.obtenir_texte_section( 0, None, cid, debut, fin )
        
        if not contenu.strip():
            if fin == None or str(fin) == '2999-01-01':
                logger.info(('Version {:'+wnbver+'} (du {} à  maintenant) non-enregistrée car vide').format(i_version+1, debut))
            else:
                logger.info(('Version {:'+wnbver+'} (du {} au {}) non-enregistrée car vide').format(i_version+1, debut, fin))
            erreur_version = True
            continue

        # Ajout des en-têtes et pied-de-texte
        if visas:
            contenu = visas + contenu
            visas = fs.stockage.ecrire_ressource( 'PRE', [False], '', 'Visas', visas )
        if signataires:
            contenu += signataires
            signataires = fs.stockage.ecrire_ressource( 'POST', [False], '', 'Signataires', signataires )
        if tp:
            contenu += tp
            tp = fs.stockage.ecrire_ressource( 'POST', [False], '', 'Travaux préparatoires', tp )
        if nota:
            contenu += nota
            nota = fs.stockage.ecrire_ressource( 'POST', [False], '', 'Nota', nota )

        # Enregistrement du fichier global
        fs.stockage.ecrire_texte( cid, nom_fichier, contenu )

        if not subprocess.check_output(['git', 'status', '--ignored', '-s'], cwd=dossier):
            if fin == None or str(fin) == '2999-01-01':
                logger.info(('Version {:'+wnbver+'} (du {} à  maintenant) non-enregistrée car identique à la précédente').format(i_version+1, debut))
            else:
                logger.info(('Version {:'+wnbver+'} (du {} au {}) non-enregistrée car identique à la précédente').format(i_version+1, debut, fin))
            erreur_version = True
            continue

        # Enregistrer les fichiers dans Git
        #subprocess.call(['git', 'commit', '--author="Législateur <>"', '--date="' + str(debut_datetime) + '"', '-m', 'Version consolidée au {}\n\nVersions :\n- base LEGI : {}\n- programme Archéo Lex : {}'.format(date_fr, date_base_legi, version_archeolex), '-q', '--no-status'], cwd=dossier)
        subprocess.call(['git', 'commit', '--author="Législateur <>"', '--date="' + str(debut_datetime) + '"', '-m', 'Version consolidée au {}'.format(date_fr), '-q', '--no-status'], cwd=dossier, env={ 'GIT_COMMITTER_DATE': last_update.isoformat(), 'GIT_COMMITTER_NAME': 'Législateur', 'GIT_COMMITTER_EMAIL': '' })
        
        if fin == None or str(fin) == '2999-01-01':
            logger.info(('Version {:'+wnbver+'} (du {} à  maintenant) enregistrée').format(i_version+1, debut))
        else:
            logger.info(('Version {:'+wnbver+'} (du {} au {}) enregistrée').format(i_version+1, debut, fin))
    
    if futur and not futur_debut:
        subprocess.call(['git', 'checkout', branche], cwd=dossier)

    # Optimisation du dossier git
    subprocess.call(['git', 'gc'], cwd=dossier)
    subprocess.call('rm -rf .git/hooks .git/refs/heads .git/refs/tags .git/logs .git/COMMIT_EDITMSG .git/branches', cwd=dossier, shell=True)
    subprocess.call('chmod -x .git/config', cwd=dossier, shell=True)

    # Ajout du tag de date éditoriale
    subprocess.call(['git', 'tag', last_update.strftime('%Y%m%d-%H%M%S')], cwd=dossier)

    if erreur_version:
        logger.info( 'Erreurs détectées avec des versions vides ou identiques aux précédentes : erreurs dans la base LEGI (en général) ou dans Archéo Lex, voir le fichier doc/limitations.md.' )

    if fs.fabrique_article.erreurs:
        logger.info( 'Erreurs - voir le fichier doc/limitations.md :' )
        for erreur in fs.fabrique_article.erreurs:
            logger.info( '* ' + erreur )

    return dossier_final, nom_final, cid

# vim: set ts=4 sw=4 sts=4 et:
