import deeplake
from deeplake.constants import MB
from deeplake.enterprise.util import raise_indra_installation_error
from deeplake.util.warnings import always_warn

import numpy as np

import uuid
from functools import partial
from typing import Optional, Any, Iterable, List, Dict, Callable, Union


def dp_filter_python(x: dict, filter: Dict) -> bool:
    """Filter helper function for Deep Lake"""
    result = [1] * len(x)

    for tensor in filter.keys():
        metadata = x[tensor].data()["value"]
        result = result and all(
            k in metadata and v == metadata[k] for k, v in filter[tensor].items()
        )

    return result


def attribute_based_filtering_python(
    view, filter: Optional[Union[Dict, Callable]] = None
):
    if filter is not None:
        if isinstance(filter, dict):
            filter = partial(dp_filter_python, filter=filter)

        view = view.filter(filter)
        # if len(view) == 0:
        #     raise ValueError(f"No data was found for {filter} metadata.")

    return view


def attribute_based_filtering_tql(view, logger, filter: Optional[Dict] = None, debug_mode=False):
    tql_filter = ""

    if filter is not None:
        if isinstance(filter, dict):
            for tensor in filter.keys():
                for key, value in filter[tensor].items():
                    val_str = f"'{value}'" if type(value) == str else f"{value}"
                    tql_filter += f"{tensor}['{key}'] == {val_str} and "
            tql_filter = tql_filter[:-5]
            
    if debug_mode:
        logger.warning(f"Converted tql string is: '{tql_filter}'")
    return view, tql_filter


# def filtering_exception(filter, exec_option):
#     if exec_option in ("compute_engine", "tensor_db") and filter is not None:
#         case_specific_exception = ""
#         if "tensor_db":
#             case_specific_exception += "To run filtering set `remote_db=False`."
#         else:
#             case_specific_exception += (
#                 """To run filtering set `exec_option="python"`."""
#             )
#         raise NotImplementedError(
#             f"Filtering data is only supported for python implementations. {case_specific_exception}"
#         )


def exact_text_search(view, query):
    view = view.filter(lambda x: query in x["text"].data()["value"])
    scores = [1.0] * len(view)

    if len(view) == 0:
        always_warn(
            "Exact text search wasn't able to find any files. Try other search options like embedding search."
        )
        index = None
    else:
        index = list(view.sample_indices)
    return (view, scores, index)


def get_id_indices(dataset, ids):
    filtered_ids = None
    view = dataset.filter(lambda x: x["ids"].data()["value"] in ids)
    filtered_ids = list(view.sample_indices)

    if len(filtered_ids) != len(ids):
        ids_that_doesnt_exist = get_ids_that_does_not_exist(ids, filtered_ids)
        raise ValueError(
            f"The following ids: {ids_that_doesnt_exist} does not exist in the dataset"
        )
    return filtered_ids


def get_ids_that_does_not_exist(ids, filtered_ids):
    ids_that_doesnt_exist = ""
    for id in ids:
        if id not in filtered_ids:
            ids_that_doesnt_exist += f"`{id}`, "
    return ids_that_doesnt_exist[:-2]


def get_filtered_ids(dataset, filter):
    filtered_ids = None
    view = dataset.filter(partial(dp_filter_python, filter=filter))
    filtered_ids = list(view.sample_indices)
    if len(filtered_ids) == 0:
        raise ValueError(f"{filter} does not exist in the dataset.")
    return filtered_ids


def get_converted_ids(dataset, filter, ids):
    if ids and filter:
        raise ValueError("Either filter or ids should be specified.")

    if ids:
        ids = get_id_indices(dataset, ids)
    else:
        ids = get_filtered_ids(dataset, filter)
    return ids