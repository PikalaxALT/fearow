import json
import math
import os
import pathlib
import random
import re
import typing

import asqlite3

from .models import PokeapiModel, collection

dbfile = pathlib.Path(__file__).parent / "db.sqlite3"


async def connect(filename: str | os.PathLike = dbfile):
    db = await asqlite3.connect(filename, uri=True)
    await PokeapiModel.prepare(db)
    db.__dict__.update(
        {
            key: value
            for key, value in PokeapiModel.classes.__dict__.items()
            if not key.startswith("__")
        }
    )
    return db


def _clean_name(name: str):
    name = name.replace("♀", "_F").replace("♂", "_M").replace("é", "e")
    name = re.sub(r"\W+", "_", name).title()
    return name


def get_name(entity: PokeapiModel, *, clean=False):
    name = entity.qualified_name
    if clean:
        name = _clean_name(name)
    return name


async def get_species(id_: int) -> "PokeapiModel.classes.PokemonSpecies":
    return await PokeapiModel.classes.PokemonSpecies.get(id_)


async def random_pokemon() -> "PokeapiModel.classes.PokemonSpecies":
    return await PokeapiModel.classes.PokemonSpecies.get_random()


async def get_default_pokemon(mon: "PokeapiModel.classes.PokemonSpecies"):
    return await (await mon.pokemons).get(is_default=True)


async def random_pokemon_name(*, clean=False):
    return get_name(await random_pokemon(), clean=clean)


async def random_move() -> "PokeapiModel.classes.Move":
    return await PokeapiModel.classes.Move.get_random()


async def random_move_name(*, clean=False):
    return get_name(await random_move(), clean=clean)


def sprite_url(dbpath: str):
    return re.sub(
        r"^/media", "https://raw.githubusercontent.com/PokeAPI/sprites/master/", dbpath
    )


def get_sprite_path(
    sprites: dict[str, typing.Union[str, dict]], *path: str
) -> typing.Optional[str]:
    try:
        for term in path:
            sprites = sprites[term]
    except (KeyError, TypeError):
        return None
    return sprites


async def get_species_sprite_url(mon: "PokeapiModel.classes.PokeomnSpecies"):
    default_poke = await get_default_pokemon(mon)
    sprites = json.loads((await default_poke.pokemon_spriteses)[0].sprites)
    options = (
        ("front_default",),
        ("versions", "generation-vii", "ultra-sun-ultra-moon", "front_default"),
        ("versions", "generation-viii", "icons", "front_default"),
    )
    for option in options:
        if path := get_sprite_path(sprites, *option):
            return sprite_url(path)


async def get_mon_types(
    mon: "PokeapiModel.classes.PokemonSpecies",
) -> list["PokeapiModel.classes.Type"]:
    default_mon = await get_default_pokemon(mon)
    return [await ptype.type for ptype in await default_mon.pokemon_types]


async def get_mon_matchup_against_type(
    mon: "PokeapiModel.classes.PokemonSpecies", type_: "PokeapiModel.classes.Type"
) -> float:
    start = 1.0
    default_mon = await get_default_pokemon(mon)
    for ptyp in await default_mon.pokemon_types:
        typ = await ptyp.type
        for efficacy in await typ.type_efficacys__target_type:
            if await efficacy.damage_type == type_:
                start *= efficacy.damage_factor / 100.0
    return start


async def get_mon_matchup_against_move(
    mon: "PokeapiModel.classes.PokemonSpecies", move: "PokeapiModel.classes.Type"
) -> float:
    types = [await move.type]
    if move.id == 560:
        types.append(await PokeapiModel.classes.Type.get(3))
    return math.prod(
        [await get_mon_matchup_against_type(mon, type_) for type_ in types]
    )


async def get_mon_matchup_against_mon(
    mon: "PokeapiModel.classes.PokemonSpecies",
    mon2: "PokeapiModel.classes.PokemonSpecies",
) -> list[float]:
    return [
        await get_mon_matchup_against_type(mon, type_)
        for type_ in await get_mon_types(mon2)
    ]


async def get_mon_learnset(
    mon: "PokeapiModel.classes.PokemonSpecies",
) -> set["PokeapiModel.classes.Move"]:
    default_pokemon = await get_default_pokemon(mon)
    return set(await pm.move for pm in await default_pokemon.pokemon_moves)


async def get_mon_learnset_with_flags(
    mon: "PokeapiModel.classes.PokemonSpecies",
) -> list["PokeapiModel.classes.PokemonMove"]:
    default_mon = await get_default_pokemon(mon)
    return await default_mon.pokemon_moves


async def mon_can_learn_move(
    mon: "PokeapiModel.classes.PokemonSpecies", move: "PokeapiModel.classes.Move"
):
    default_mon = await get_default_pokemon(mon)
    return await (await default_mon.pokemon_moves).get(move=move) is not None


async def get_mon_abilities_with_flags(
    mon: "PokeapiModel.classes.PokemonSpecies",
) -> collection["PokeapiModel.classes.PokemonAbility"]:
    default_mon = await get_default_pokemon(mon)
    return await default_mon.pokemon_abilitys


async def get_mon_abilities(
    mon: "PokeapiModel.classes.PokemonSpecies",
) -> list["PokeapiModel.classes.Ability"]:
    pokemon_abilities = await get_mon_abilities_with_flags(mon)
    return [await pab.ability for pab in pokemon_abilities]


async def mon_has_ability(
    mon: "PokeapiModel.classes.PokemonSpecies", ability: "PokeapiModel.classes.Ability"
) -> bool:
    return (
        await (await get_mon_abilities_with_flags(mon)).get(ability=ability) is not None
    )


async def mon_has_type(
    mon: "PokeapiModel.classes.PokemonSpecies", type_: "PokeapiModel.classes.Type"
) -> bool:
    default_mon = await get_default_pokemon(mon)
    return await (await default_mon.pokemon_types).get(type=type_) is not None


async def has_mega_evolution(mon: "PokeapiModel.classes.PokemonSpecies") -> bool:
    for poke in await mon.pokemons:
        if await (await poke.pokemon_forms).get(is_mega=True) is not None:
            return True
    return False


async def get_evo_line(
    mon: "PokeapiModel.classes.PokemonSpecies",
) -> collection["PokeapiModel.classes.PokemonSpecies"]:
    return await (await mon.evolution_chain).pokemon_species


async def has_evos(mon: "PokeapiModel.classes.PokemonSpecies") -> bool:
    return len(await get_evo_line(mon)) > 1


async def is_in_evo_line(
    needle: "PokeapiModel.classes.PokemonSpecies",
    haystack: "PokeapiModel.classes.PokemonSpecies",
) -> bool:
    return needle in await get_evo_line(haystack)


async def has_branching_evos(mon: "PokeapiModel.classes.PokemonSpecies") -> bool:
    return any(
        [len(await poke.evolves_into_species) > 1 for poke in await get_evo_line(mon)]
    )


async def mon_is_in_dex(
    mon: "PokeapiModel.classes.PokemonSpecies", dex: "PokeapiModel.classes.Pokedex"
) -> bool:
    return await (await mon.pokemon_dex_numbers.get(pokedex=dex)) is not None


async def get_default_forme(
    mon: "PokeapiModel.classes.PokemonSpecies",
) -> "PokeapiModel.classes.PokemonForm":
    for poke in await mon.pokemons:
        if form := await (await poke.pokemon_forms).get(is_default=True):
            return form


async def get_base_stats(mon: "PokeapiModel.classes.PokemonSpecies") -> dict[str, int]:
    default_mon = await get_default_pokemon(mon)
    return {
        (await bs.stat).qualified_name: bs.base_stat
        for bs in await default_mon.pokemon_stats
    }


async def get_egg_groups(
    mon: "PokeapiModel.classes.PokemonSpecies",
) -> list["PokeapiModel.classes.EggGroup"]:
    return [await peg.egg_group for peg in await mon.pokemon_egg_groups]


async def mon_is_in_egg_group(
    mon: "PokeapiModel.classes.PokemonSpecies",
    egg_group: "PokeapiModel.classes.EggGroup",
) -> bool:
    return egg_group in await get_egg_groups(mon)


async def mon_can_mate_with(
    mon: "PokeapiModel.classes.PokemonSpecies",
    mate: "PokeapiModel.classes.PokemonSpecies",
) -> bool:
    # Babies can't breed
    if mon.is_baby or mate.is_baby:
        return False

    # Undiscovered can't breed together, and Ditto can't breed Ditto
    # Other than that, same species can breed together.
    if mon.id == mate.id:
        return (
            mon.id != 132
            and mon.gender_rate not in {0, 8, -1}
            and not await mon_is_in_undiscovered_egg_group(mon)
        )

    # Anything that's not undiscovered can breed with Ditto
    if mon.id == 132 or mate.id == 132:
        if mon.id == 132:
            mon = mate
        return not await mon_is_in_undiscovered_egg_group(mon)

    # All-male and all-female species can't breed with each other,
    # and genderless species can't breed except with Ditto.
    if (
        mon.gender_rate == mate.gender_rate == 0
        or mon.gender_rate == mate.gender_rate == 8
        or -1 in {mon.gender_rate, mate.gender_rate}
    ):
        return False

    # If the two species share egg groups, we good.
    mon_egg_groups = await get_egg_groups(mon)
    mate_egg_groups = await get_egg_groups(mate)
    return any(grp in mon_egg_groups for grp in mate_egg_groups)


async def get_mon_flavor_text(
    mon: "PokeapiModel.classes.PokemonSpecies",
    version: "PokeapiModel.classes.Version" = None,
) -> str:
    flavor_texts = await mon.pokemon_species_flavor_texts
    if version:
        return (await flavor_texts.get(language_id=9, version=version)).flavor_text
    return random.choice(
        [txt.flavor_text for txt in flavor_texts if txt.language_id == 9]
    )


async def get_mon_evolution_methods(
    mon: "PokeapiModel.classes.PokemonSpecies",
) -> list["PokeapiModel.classes.PokemonEvolution"]:
    return [await poke.pokemon_evolution for poke in await mon.evolves_into_species]


async def mon_is_in_undiscovered_egg_group(
    mon: "PokeapiModel.classes.PokemonSpecies",
) -> bool:
    return await (await mon.pokemon_egg_groups).get(egg_group_id=15) is not None


async def get_move_attrs(
    move: "PokeapiModel.classes.Move",
) -> list["PokeapiModel.classes.MoveAttribute"]:
    return [await mam.move_attribute for mam in await move.move_attribute_maps]


async def get_move_description(
    move: "PokeapiModel.classes.Move", version: "PokeapiModel.classes.Version" = None
) -> str:
    flavor_texts = await move.move_flavor_texts
    if version:
        return (await flavor_texts.get(language_id=9, version=version)).flavor_text
    return random.choice(
        [txt.flavor_text for txt in flavor_texts if txt.language_id == 9]
    )
