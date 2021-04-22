# Fearow
Thin async ORM for local access to a PokeAPI SQLite Database

Also comes with a lite async sqlite3 wrapper called `asqlite`, based on [aiosqlite](https://github.com/omnilib/aiosqlite) but using a [`concurrent.futures.ThreadPoolExecutor`](https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ThreadPoolExecutor).

![](https://images.gameinfo.io/pokemon/256/022-00.png)

## Package design
The ORM is centered around the `PokeapiModel` class, which is a specialized replica of sqlalchemy's automap base with async-compatible lazy loading. I achieve this using [`asyncstdlib.functools.cached_property`](https://asyncstdlib.readthedocs.io/en/latest/source/api/functools.html#asyncstdlib.functools.cached_property) for all attributes that reference other tables in PokeAPI.

`PokeapiModel` has an attribute `classes` which contains the mapped classes. The sqlite table `pokemon_v2_pokemonspecies` is mapped to `PokeapiModel.classes.PokemonSpecies`, etc. Each mapped class has four kinds of attributes:
1. **Column-mapped attributes**, which take the name of the sqlite column. These are accessed in the usual manner.
2. **Relationships**, these are async cached properties which will lazy fetch an instance representing the referenced row. If a table has column `pokemon_species_id`, for example, the relationship name will be `pokemon_species`.
3. **Backrefs**, these are async cached properties which will lazy fetch a list of all rows in the foreign table referencing this row. Its name will be a pluralized form of the foreign table name with underscores inserted between English words i.e. `pokemon_v2_pokemonspeciesname` --> `PokemonSpecies.pokemon_species_names`. If the foreign table has two columns referencing the same table, the backref will be modified by appending two underscores followed by the name of the foreign attribute, i.e. `Type.type_efficacys__damage_type`. The returned list is of type `collection` and has an async method `.get` which functions like [`discord.utils.get`](https://discordpy.readthedocs.io/en/latest/api.html#discord.utils.get) which supports both column and relationship lookups.
4. `.qualified_name` is a special case. If an object has rows in a table of names, this attribute will be the English name from that table referencing the given row, else `None`.

## Requirements
Python 3.6 or newer with all the packages listed in requirements.txt. You should also clone [PokeAPI](/PokeAPI/pokeapi) recursively and follow its instructions to build the local SQLite database.

## Usage in scripts
```py
import asyncio
import fearow

async def main():
    db = await fearow.connect('path/to/pokeapi/db.sqlite3')
    pikachu = await fearow.get_species(25)
    haunter = await fearow.get_species_named('Haunter')
    move = await db.Move.get_named('Perish Song')
    if await (await haunter.pokemon_moves).get(move=move):  # Note the double await!!
        print('{} can learn {}'.format(haunter, move))
    else:
        print('{} cannot learn {}'.format(haunter, move))

asyncio.run(main())
```
