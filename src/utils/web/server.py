import json
import pathlib
import aiofiles


__all__ = (
    "write_web",
    "read_web",
)


async def write_web(file: str, user_id: int, template: dict, timestamp: int) -> None:
    """
    template should always include user_id
    """
    # write to file here
    new_dict = {"user_id": user_id}
    for x in template:
        new_dict[x] = template[x]

    pathlib.Path(pathlib.Path.cwd() / "data" / "web" /
                 file / str(user_id)).mkdir(exist_ok=True)
    pathlib.Path(pathlib.Path.cwd() / "data" / "web" / file /
                 str(user_id) / f"{timestamp}.json").touch(exist_ok=True)

    async with aiofiles.open(pathlib.Path.cwd() / "data" / "web" / file / str(user_id) / f"{timestamp}.json", "w+") as f:
        await f.write(json.dumps(new_dict))


async def read_web(file: str, user_id: int, timestamp: int) -> dict:
    async with aiofiles.open(pathlib.Path.cwd() / "data" / "web" / file / str(user_id) / f"{timestamp}.json", "r") as f:
        return json.loads(await f.read())
