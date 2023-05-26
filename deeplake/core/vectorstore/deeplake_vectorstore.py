import deeplake
from deeplake.constants import (
    DEFAULT_VECTORSTORE_DEEPLAKE_PATH,
    DEFAULT_VECTORSTORE_TENSORS,
)
from deeplake.core.dataset import Dataset as DeepLakeDataset
from deeplake.core.vectorstore.vector_search import utils
from deeplake.core.vectorstore.vector_search import dataset as dataset_utils
from deeplake.core.vectorstore.vector_search import filter as filter_utils
from deeplake.core import vectorstore


try:
    from indra import api  # type: ignore

    _INDRA_INSTALLED = True
except Exception:  # pragma: no cover
    _INDRA_INSTALLED = False  # pragma: no cover

import logging
from typing import Optional, Any, Iterable, List, Dict, Union, Callable

import numpy as np


logger = logging.getLogger(__name__)


class DeepLakeVectorStore:
    """Base class for DeepLakeVectorStore"""

    def __init__(
        self,
        dataset_path: str = DEFAULT_VECTORSTORE_DEEPLAKE_PATH,
        token: Optional[str] = None,
        tensors_dict: List[Dict[str, str]] = DEFAULT_VECTORSTORE_TENSORS,
        embedding_function: Optional[Callable] = None,
        read_only: Optional[bool] = False,
        ingestion_batch_size: int = 1024,
        num_workers: int = 0,
        exec_option: str = "python",
        verbose=False,
        **kwargs: Any,
    ) -> None:
        """DeepLakeVectorStore initialization

        Args:
            dataset_path (str): path to the deeplake dataset. Defaults to DEFAULT_VECTORSTORE_DEEPLAKE_PATH.
            token (str, optional): Activeloop token, used for fetching credentials for Deep Lake datasets. This is Optional, tokens are normally autogenerated. Defaults to None.
            tensors_dict (List[Dict[str, str]], optional): List of dictionaries that contains information about tensors that user wants to create. Defaults to
            embedding_function (Optional[callable], optional): Function that converts query into embedding. Defaults to None.
            read_only (bool, optional):  Opens dataset in read-only mode if this is passed as True. Defaults to False.
            ingestion_batch_size (int): The batch size to use during ingestion. Defaults to 1024.
            num_workers (int): The number of workers to use for ingesting data in parallel. Defaults to 0.
            exec_option (str): Type of query execution. It could be either "python", "compute_engine" or "tensor_db". Defaults to "python".
                - ``python`` - Pure-python implementation that runs on the client and can be used for data stored anywhere. WARNING: using this option with big datasets is discouraged because it can lead to memory issues.
                - ``compute_engine`` - C++ implementation of the Deep Lake Compute Engine that runs on the client and can be used for any data stored in or connected to Deep Lake. It cannot be used with in-memory or local data.
                - ``tensor_db`` - Fully-hosted Managed Database that is responsible for storage and query execution. Only available for data stored in the Deep Lake Managed Database. This is achieved by specifying runtime = {"tensor_db": True} during dataset creation.
            verbose (bool): Whether to print summary of the dataset created. Defaults to False.
            **kwargs (Any): Additional keyword arguments.
        """
        self.ingestion_batch_size = ingestion_batch_size
        self.num_workers = num_workers
        creds = {"creds": kwargs["creds"]} if "creds" in kwargs else {}
        self.dataset = dataset_utils.create_or_load_dataset(
            dataset_path,
            token,
            creds,
            logger,
            read_only,
            exec_option,
            embedding_function,
            **kwargs,
        )
        self.embedding_function = embedding_function
        self._exec_option = exec_option
        self.verbose = verbose

    def add(
        self,
        texts: Iterable[str],
        embedding_function: Optional[Callable] = None,
        metadatas: Optional[List[dict]] = None,
        ids: Optional[List[str]] = None,
        embeddings: Optional[Union[List[float], np.ndarray]] = None,
        total_samples_processed: int = 0,
    ) -> List[str]:
        """Adding elements to deeplake vector store

        Args:
            texts (Iterable[str]): texts to add to deeplake vector store
            embedding_function (callable, optional): embedding function used to convert document texts into embeddings.
            metadatas (List[dict], optional): List of metadatas. Defaults to None.
            ids (List[str], optional): List of document IDs. Defaults to None.
            embeddings (Union[List[float], np.ndarray], optional): embedding of texts. Defaults to None.
            total_samples_processed (int): Total number of samples processed before transforms stopped.

        Returns:
            List[str]: List of document IDs
        """
        processed_tensors, ids = dataset_utils.preprocess_tensors(
            ids, texts, metadatas, embeddings
        )
        assert ids is not None

        dataset_utils.extend_or_ingest_dataset(
            processed_tensors=processed_tensors,
            dataset=self.dataset,
            embedding_function=embedding_function or self.embedding_function,
            ingestion_batch_size=self.ingestion_batch_size,
            num_workers=self.num_workers,
            total_samples_processed=total_samples_processed,
        )

        self.dataset.commit(allow_empty=True)
        if self.verbose:
            self.dataset.summary()
        return ids

    def search(
        self,
        prompt: Optional[str] = None,
        embedding_function: Optional[Callable] = None,
        embedding: Optional[Union[List[float], np.ndarray]] = None,
        k: int = 4,
        distance_metric: str = "L2",
        query: Optional[str] = None,
        filter: Optional[Union[Dict, Callable]] = None,
        exec_option: Optional[str] = "python",
        embedding_tensor: str = "embedding",
    ):
        """DeepLakeVectorStore search method that combines embedding search, metadata search, and custom TQL search.

        Args:
            prompt (Optional[str], optional): String representation of the prompt to embed using embedding_function. Defaults to None. The prompt and embedding cannot both be specified or both be None.
            embedding_function (callable, optional): function for converting prompt into embedding. Only valid if promps is specified
            embedding (Union[np.ndarray, List[float]], optional): Embedding representation for performing the search. Defaults to None. The prompt and embedding cannot both be specified or both be None.
            k (int): Number of elements to return after running query. Defaults to 4.
            distance_metric (str): Type of distance metric to use for sorting the data. Avaliable options are: "L1", "L2", "COS", "MAX". Defaults to "L2".
            query: Optional[str] = None,
            filter (Union[Dict, Callable], optional): Additional filter evaluated prior to the embedding search.
                - ``Dict`` - Key-value search on any tensor of htype json. Dict = {"tensor_name_1": {"key": value}, "tensor_name_2": {"key": value}}
                - ``Function`` - Any function that is compatible with `deeplake.filter`.
            exec_option (str, optional): Type of query execution. It could be either "python", "compute_engine" or "tensor_db". Defaults to "python".
                - ``python`` - Pure-python implementation that runs on the client and can be used for data stored anywhere. WARNING: using this option with big datasets is discouraged because it can lead to memory issues.
                - ``compute_engine`` - Performant C++ implementation of the Deep Lake Compute Engine that runs on the client and can be used for any data stored in or connected to Deep Lake. It cannot be used with in-memory or local datasets.
                - ``tensor_db`` - Performant and fully-hosted Managed Tensor Database that is responsible for storage and query execution. Only available for data stored in the Deep Lake Managed Database. Store datasets in this database by specifying runtime = {"db_engine": True} during dataset creation.
            embedding_tensor (str): Name of tensor with embeddings. Defaults to "embedding".


        Raises:
            ValueError: When invalid execution option is specified
            NotImplementedError: When unsupported combinations of parameters are specified

        Returns:
            Dict: Dictionary where keys are tensor names and values are the results of the search
        """
        exec_option = exec_option or self._exec_option
        if exec_option not in ("python", "compute_engine", "tensor_db"):
            raise ValueError(
                "Invalid `exec_option` it should be either `python`, `compute_engine` or `tensor_db`."
            )

        if embedding_function is None and embedding is None:
            view, scores, indices = filter_utils.exact_text_search(self.dataset, prompt)
        else:
            query_emb = dataset_utils.get_embedding(
                embedding,
                prompt,
                embedding_function=embedding_function,
            )

        runtime = utils.get_runtime_from_exec_option(exec_option)

        if exec_option == "python":
            if query is not None:
                raise NotImplementedError(
                    f"User-specified TQL queries are not support for exec_option={exec_option} "
                )

            view = filter_utils.attribute_based_filtering_python(self.dataset, filter)

            embeddings = dataset_utils.fetch_embeddings(
                exec_option=exec_option,
                view=view,
                logger=logger,
                embedding_tensor=embedding_tensor,
            )

            return vectorstore.python_vector_search(
                deeplake_dataset=view,
                query_embedding=query_emb,
                embeddings=embeddings,
                distance_metric=distance_metric.lower(),
                k=k,
            )
        else:
            if type(filter) == Callable:
                raise NotImplementedError(
                    f"UDF filter function are not supported with exec_option={exec_option}"
                )
            if query and filter:
                raise NotImplementedError(
                    f"query and filter parameters cannot be specified simultaneously."
                )

            utils.check_indra_installation(
                exec_option, indra_installed=_INDRA_INSTALLED
            )

            view, tql_filter = filter_utils.attribute_based_filtering_tql(
                self.dataset, filter
            )

            return vectorstore.vector_search(
                query_embedding=query_emb,
                distance_metric=distance_metric.lower(),
                deeplake_dataset=view,
                k=k,
                tql_string=query,
                tql_filter=tql_filter,
                embedding_tensor=embedding_tensor,
                runtime=runtime,
            )

    def delete(
        self,
        ids: Optional[List[str]] = None,
        filter: Optional[Dict[str, str]] = None,
        delete_all: Optional[bool] = None,
    ) -> bool:
        """Delete the entities in the dataset
        Args:
            ids (Optional[List[str]]): The document_ids to delete.
                Defaults to None.
            filter (Optional[Dict[str, str]]): The filter to delete by.
                Defaults to None.
            delete_all (Optional[bool]): Whether to drop the dataset.
                Defaults to None.
        """
        self.dataset, dataset_deleted = dataset_utils.delete_all_samples_if_specified(
            self.dataset, delete_all
        )
        if dataset_deleted:
            return True

        ids = filter_utils.get_converted_ids(self.dataset, filter, ids)
        dataset_utils.delete_and_commit(self.dataset, ids)
        return True

    @staticmethod
    def force_delete_by_path(path: str) -> None:
        """Force delete dataset by path"""
        deeplake.delete(path, large_ok=True, force=True)

    def __len__(self):
        return len(self.dataset)