# Query: https://w.wiki/4Z73
PROPS_FAMILY = {
    "P7": "sibling",
    "P9": "sibling",
    "P22": "parent",
    "P26": "spouse",
    "P25": "parent",
    "P40": "child",
    "P43": "stepparent",
    "P44": "stepparent",
    "P451": "unmarried partner",
    "P1038": "relative",
    "P1290": "godparent",
    "P3373": "sibling",
    "P3448": "stepparent",
    "P8810": "unspecified parent",
}

PROPS_ASSOCIATION = {
    "P1327": "partner in business or sport",
    "P3342": "significant person",
}

# https://www.wikidata.org/wiki/Wikidata:List_of_properties/human
PROPS_DIRECT = {
    "P1477": "alias",  # birth name
    "P1813": "alias",  # short name
    "P2561": "alias",  # name
    "P1559": "alias",  # name in native language
    "P2562": "alias",  # married name
    "P511": "title",
    "P735": "firstName",
    "P734": "lastName",
    "P1950": "lastName",
    "P21": "gender",
    "P39": "position",
    "P140": "religion",
    "P106": "topics",
    "P569": "birthDate",
    "P5056": "fatherName",
    "P570": "deathDate",
    "P19": "birthPlace",
    "P856": "website",
    "P512": "education",
    "P69": "education",
    "P27": "nationality",
    "P742": "weakAlias",
    "P172": "ethnicity",
    "P973": "sourceUrl",
    "P1278": "leiCode",
    "P17": "country",
    "P571": "incorporationDate",
    "P1454": "legalForm",
}

PROPS_QUALIFIED = (
    "position",
    "education",
)

PROPS_TOPICS = {
    "Q82955": "role.pep",
    "Q193391": "role.diplo",
    "Q392651": "role.spy",
    "Q14886050": "crime.terror",
    "Q16533": "role.judge",
}
