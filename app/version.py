"""Version du logiciel — source unique.

Lue par `build_exe.py` (metadonnees du .exe), `installer.iss` (numero de
version de l'installateur, qui pilote les mises a jour Windows) et exposee
par l'API pour l'ecran « A propos ».

Format `MAJEUR.MINEUR.CORRECTIF` : Windows exige trois nombres pour comparer
deux installations.
"""
VERSION = "1.0.0"
# Nom commercial. Il pilote le nom de l'executable, celui de l'installateur et
# le titre de la fenetre. Il ne pilote PAS le dossier de donnees : celui-ci est
# fige dans app/paths.py, sans quoi une base existante deviendrait invisible.
APP_NAME = "Wealfy"
# Editeur affiche par Windows dans les proprietes du .exe et par l'installateur.
# C'est le nom du PROJET et non celui de l'auteur : le depot est public, et un
# nom de personne n'a pas a etre lu par tous ceux qui telechargent le logiciel.
PUBLISHER = "Wealfy"
DESCRIPTION = "Gestion patrimoniale locale"
