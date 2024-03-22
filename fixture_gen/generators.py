from faker import Faker
from followthemoney import model
import json
import random
from tempfile import NamedTemporaryFile


def switch_random_character(s: str) -> str:
    """
    Switch two random characters in a string.
    Joe Biden -> Jeo Biden
    """
    if len(s) == 0:
        return s
    i = random.randint(1, len(s) - 1)
    return s[: i - 1] + s[i] + s[i - 1] + s[i + 1 :]


def second_name_last_name_first_names(s: str) -> str:
    """
    Switch the first and last names of a person, joining with a comma.
    Joe Biden -> Biden, Joe
    Pablo Ruiz Picasso -> Ruiz Picasso, Pablo
    """
    if len(s) == 0:
        return s
    names = s.split(" ")
    if len(names) < 2:
        return s
    return " ".join(names[1:]) + ", " + names[0]


def replace_spaces_with_special_char(s: str) -> str:
    """
    Replace all spaces with a non-breaking space.
    Pablo Picasso -> Pablo\u00a0Picasso
    """
    return s.replace(" ", " ")


def replace_non_ascii_with_special_char(s: str) -> str:
    """
    Replace all non-ascii characters with a special char.
    Schrödinger -> Schr?dinger
    """
    return "".join([c if ord(c) < 128 else "?" for c in s])


def replace_double_character_with_single(s: str) -> str:
    """
    Replace all double characters with a single character.
    Pablo Picasso -> Pablo Picaso
    """
    return "".join([c for i, c in enumerate(s) if i == 0 or s[i - 1] != c])


def remove_special_characters(s: str) -> str:
    """
    Remove all special characters.
    Schrödinger -> Schrdinger
    """
    return "".join([c if ord(c) < 128 else "" for c in s])


def duplicate_random_character(s: str) -> str:
    """
    Duplicate a random character in a string.
    Pablo Picasso -> Pabblo Picasso
    """
    if len(s) == 0:
        return s
    i = random.randint(0, len(s) - 1)
    return s[:i] + s[i] + s[i:]


def replace_random_vowel(s: str) -> str:
    """
    Replace a random vowel with another vowel.
    Pablo Picasso -> Pabla Picasso
    """
    vowels = "aeiouy"
    if len(s) == 0:
        return s
    i = random.randint(0, len(s) - 1)
    if s[i] in vowels:
        return s[:i] + random.choice(vowels) + s[i + 1 :]
    return s


treatments = {
    "switch_random_character": switch_random_character,
    "second_name_last_name_first_names": second_name_last_name_first_names,
    "replace_spaces_with_special_char": replace_spaces_with_special_char,
    "replace_non_ascii_with_special_char": replace_non_ascii_with_special_char,
    "replace_double_character_with_single": replace_double_character_with_single,
    "remove_special_characters": remove_special_characters,
    "duplicate_random_character": duplicate_random_character,
    "replace_random_vowel": replace_random_vowel,
}


class PersonGenerator:
    def __init__(self):
        self.fake = Faker()

    def generate(self):
        entity = model.make_entity("Person")
        entity.add("name", self.fake.name())
        entity.id = self.fake.uuid4()
        return entity


def write_pair(f, original: dict, changed: dict, treatment: str):
    json.dump(
        {
            "original": original,
            "changed": changed,
            "treatment": treatment,
        },
        f,
    )


def create_fixtures_with_treatment(
    treatment: str,
    fname: str,
    n: int = 10,
):
    if treatment not in treatments:
        raise ValueError(f"Unknown treatment: {treatment}")
    with open(fname, mode="w") as f:
        for _ in range(0, n):
            person = PersonGenerator().generate()
            changed = person.clone()
            fn = treatments[treatment]
            changed.set("name", fn(person.get("name")[0]))
            write_pair(f, person.to_dict(), changed.to_dict(), treatment)
