import typing


def blank_row(shape) -> dict:
    empty = {}
    for field, annotation in shape.__annotations__.items():
        kinds = typing.get_args(annotation) or (annotation,)
        if type(None) in kinds:
            empty[field] = None
        elif str in kinds:
            empty[field] = ""
        else:
            empty[field] = 0.0
    return empty


def catalog_rows(names, shape) -> list:
    return [shape.from_server(dict(blank_row(shape), id=index + 1, name=name))
            for index, name in enumerate(names)]
