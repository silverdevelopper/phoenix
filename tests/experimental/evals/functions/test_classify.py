import json
from contextlib import ExitStack
from itertools import product
from typing import List
from unittest.mock import MagicMock, patch

import httpx
import numpy as np
import pandas as pd
import phoenix
import pytest
import respx
from pandas.core.frame import DataFrame
from pandas.testing import assert_frame_equal
from phoenix.experimental.evals import (
    NOT_PARSABLE,
    OpenAIModel,
    llm_classify,
    run_relevance_eval,
)
from phoenix.experimental.evals.evaluators import LLMEvaluator
from phoenix.experimental.evals.functions.classify import (
    run_evals,
)
from phoenix.experimental.evals.templates.default_templates import (
    RAG_RELEVANCY_PROMPT_TEMPLATE,
    TOXICITY_PROMPT_TEMPLATE,
)
from phoenix.experimental.evals.utils import _EXPLANATION, _FUNCTION_NAME, _RESPONSE
from respx.patterns import M


@pytest.fixture
def toxicity_evaluator(openai_model: OpenAIModel) -> LLMEvaluator:
    return LLMEvaluator(
        template=TOXICITY_PROMPT_TEMPLATE,
        model=openai_model,
    )


@pytest.fixture
def relevance_evaluator(openai_model: OpenAIModel) -> LLMEvaluator:
    return LLMEvaluator(
        template=RAG_RELEVANCY_PROMPT_TEMPLATE,
        model=openai_model,
    )


@pytest.fixture(
    params=[
        pytest.param(True, id="running_event_loop_exists"),
        pytest.param(False, id="no_running_event_loop_exists"),
    ]
)
def running_event_loop_mock(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> bool:
    running_event_loop_exists = request.param
    monkeypatch.setattr(
        "phoenix.experimental.evals.functions.executor._running_event_loop_exists",
        lambda: running_event_loop_exists,
    )
    assert (
        phoenix.experimental.evals.functions.executor._running_event_loop_exists()
    ) is running_event_loop_exists, "mocked function should return the expected value"
    return running_event_loop_exists


@pytest.fixture
def classification_dataframe():
    return pd.DataFrame(
        [
            {
                "input": "What is Python?",
                "reference": "Python is a programming language.",
            },
            {
                "input": "What is Python?",
                "reference": "Ruby is a programming language.",
            },
            {"input": "What is C++?", "reference": "C++ is a programming language."},
            {"input": "What is C++?", "reference": "irrelevant"},
        ],
    )


@pytest.fixture
def classification_responses():
    return [
        "relevant",
        "irrelevant",
        "relevant",
        "irrelevant",
    ]


@pytest.fixture
def classification_template():
    return RAG_RELEVANCY_PROMPT_TEMPLATE


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_llm_classify(
    openai_api_key: str,
    classification_dataframe: DataFrame,
    respx_mock: respx.mock,
):
    dataframe = classification_dataframe
    keys = list(zip(dataframe["input"], dataframe["reference"]))
    responses = ["relevant", "irrelevant", "\nrelevant ", "unparsable"]
    response_mapping = {key: response for key, response in zip(keys, responses)}

    for (query, reference), response in response_mapping.items():
        matcher = M(content__contains=query) & M(content__contains=reference)
        payload = {
            "choices": [
                {
                    "message": {
                        "content": response,
                    },
                }
            ],
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    with patch.object(OpenAIModel, "_init_tiktoken", return_value=None):
        model = OpenAIModel()

    result = llm_classify(
        dataframe=dataframe,
        template=RAG_RELEVANCY_PROMPT_TEMPLATE,
        model=model,
        rails=["relevant", "irrelevant"],
        verbose=True,
    )

    expected_labels = ["relevant", "irrelevant", "relevant", NOT_PARSABLE]
    assert result.iloc[:, 0].tolist() == expected_labels
    assert_frame_equal(
        result,
        pd.DataFrame(
            data={"label": expected_labels},
        ),
    )


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_llm_classify_with_included_prompt_and_response(
    openai_api_key: str,
    classification_dataframe: DataFrame,
    respx_mock: respx.mock,
):
    dataframe = classification_dataframe
    keys = list(zip(dataframe["input"], dataframe["reference"]))
    responses = ["relevant", "irrelevant", "\nrelevant ", "unparsable"]
    response_mapping = {key: response for key, response in zip(keys, responses)}

    for (query, reference), response in response_mapping.items():
        matcher = M(content__contains=query) & M(content__contains=reference)
        payload = {
            "choices": [
                {
                    "message": {
                        "content": response,
                    },
                }
            ],
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    with patch.object(OpenAIModel, "_init_tiktoken", return_value=None):
        model = OpenAIModel()

    result = llm_classify(
        dataframe=dataframe,
        template=RAG_RELEVANCY_PROMPT_TEMPLATE,
        model=model,
        rails=["relevant", "irrelevant"],
        verbose=True,
        include_prompt=True,
        include_response=True,
    )

    expected_labels = ["relevant", "irrelevant", "relevant", NOT_PARSABLE]
    assert result.iloc[:, 0].tolist() == expected_labels
    assert result["label"].tolist() == expected_labels
    assert result["response"].tolist() == responses
    output_prompts = result["prompt"].tolist()
    inputs = dataframe["input"].tolist()
    references = dataframe["reference"].tolist()
    assert all(input in prompt for input, prompt in zip(inputs, output_prompts))
    assert all(reference in prompt for reference, prompt in zip(references, output_prompts))


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_llm_classify_with_async(
    openai_api_key: str, classification_dataframe: DataFrame, respx_mock: respx.mock
):
    dataframe = classification_dataframe
    keys = list(zip(dataframe["input"], dataframe["reference"]))
    responses = ["relevant", "irrelevant", "\nrelevant ", "unparsable"]
    response_mapping = {key: response for key, response in zip(keys, responses)}

    for (query, reference), response in response_mapping.items():
        matcher = M(content__contains=query) & M(content__contains=reference)
        payload = {
            "choices": [
                {
                    "message": {
                        "content": response,
                    },
                }
            ],
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    with patch.object(OpenAIModel, "_init_tiktoken", return_value=None):
        model = OpenAIModel()

    result = llm_classify(
        dataframe=dataframe,
        template=RAG_RELEVANCY_PROMPT_TEMPLATE,
        model=model,
        rails=["relevant", "irrelevant"],
        verbose=True,
    )

    expected_labels = ["relevant", "irrelevant", "relevant", NOT_PARSABLE]
    assert result.iloc[:, 0].tolist() == expected_labels
    assert_frame_equal(
        result,
        pd.DataFrame(
            data={"label": expected_labels},
        ),
    )


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_llm_classify_with_fn_call(
    openai_api_key: str, classification_dataframe: DataFrame, respx_mock: respx.mock
):
    dataframe = classification_dataframe
    keys = list(zip(dataframe["input"], dataframe["reference"]))
    responses = ["relevant", "irrelevant", "\nrelevant ", "unparsable"]
    response_mapping = {key: response for key, response in zip(keys, responses)}

    for (query, reference), response in response_mapping.items():
        matcher = M(content__contains=query) & M(content__contains=reference)
        payload = {
            "choices": [{"message": {"function_call": {"arguments": {"response": response}}}}]
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    with patch.object(OpenAIModel, "_init_tiktoken", return_value=None):
        model = OpenAIModel(max_retries=0)

    result = llm_classify(
        dataframe=dataframe,
        template=RAG_RELEVANCY_PROMPT_TEMPLATE,
        model=model,
        rails=["relevant", "irrelevant"],
    )

    expected_labels = ["relevant", "irrelevant", "relevant", NOT_PARSABLE]
    assert result.iloc[:, 0].tolist() == expected_labels
    assert_frame_equal(result, pd.DataFrame(data={"label": expected_labels}))


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_classify_fn_call_no_explain(
    openai_api_key: str, classification_dataframe: DataFrame, respx_mock: respx.mock
):
    dataframe = classification_dataframe
    keys = list(zip(dataframe["input"], dataframe["reference"]))
    responses = ["relevant", "irrelevant", "\nrelevant ", "unparsable"]
    response_mapping = {key: response for key, response in zip(keys, responses)}

    for (query, reference), response in response_mapping.items():
        matcher = M(content__contains=query) & M(content__contains=reference)
        payload = {
            "choices": [{"message": {"function_call": {"arguments": {"response": response}}}}]
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    with patch.object(OpenAIModel, "_init_tiktoken", return_value=None):
        model = OpenAIModel(max_retries=0)

    result = llm_classify(
        dataframe=dataframe,
        template=RAG_RELEVANCY_PROMPT_TEMPLATE,
        model=model,
        rails=["relevant", "irrelevant"],
        provide_explanation=True,
    )

    expected_labels = ["relevant", "irrelevant", "relevant", NOT_PARSABLE]
    assert result.iloc[:, 0].tolist() == expected_labels
    assert_frame_equal(
        result,
        pd.DataFrame(data={"label": expected_labels, "explanation": [None, None, None, None]}),
    )


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_classify_fn_call_explain(
    openai_api_key: str, classification_dataframe: DataFrame, respx_mock: respx.mock
):
    dataframe = classification_dataframe
    keys = list(zip(dataframe["input"], dataframe["reference"]))
    responses = ["relevant", "irrelevant", "\nrelevant ", "unparsable"]
    response_mapping = {key: response for key, response in zip(keys, responses)}

    for ii, ((query, reference), response) in enumerate(response_mapping.items()):
        matcher = M(content__contains=query) & M(content__contains=reference)
        message = {
            "function_call": {
                "arguments": f"{{\n  \042response\042: \042{response}\042, \042explanation\042: \042{ii}\042\n}}"  # noqa E501
            }
        }
        respx_mock.route(matcher).mock(
            return_value=httpx.Response(200, json={"choices": [{"message": message}]})
        )

    with patch.object(OpenAIModel, "_init_tiktoken", return_value=None):
        model = OpenAIModel(max_retries=0)

    result = llm_classify(
        dataframe=dataframe,
        template=RAG_RELEVANCY_PROMPT_TEMPLATE,
        model=model,
        rails=["relevant", "irrelevant"],
        provide_explanation=True,
    )

    expected_labels = ["relevant", "irrelevant", "relevant", NOT_PARSABLE]
    assert result.iloc[:, 0].tolist() == expected_labels
    assert_frame_equal(
        result,
        pd.DataFrame(data={"label": expected_labels, "explanation": ["0", "1", "2", "3"]}),
    )


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_llm_classify_prints_to_stdout_with_verbose_flag(
    classification_dataframe: DataFrame,
    openai_api_key: str,
    respx_mock: respx.mock,
    capfd: pytest.CaptureFixture[str],
):
    dataframe = classification_dataframe
    keys = list(zip(dataframe["input"], dataframe["reference"]))
    responses = ["relevant", "irrelevant", "\nrelevant ", "unparsable"]
    response_mapping = {key: response for key, response in zip(keys, responses)}

    for (query, reference), response in response_mapping.items():
        matcher = M(content__contains=query) & M(content__contains=reference)
        payload = {"choices": [{"message": {"content": response}}]}
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    with patch.object(OpenAIModel, "_init_tiktoken", return_value=None):
        model = OpenAIModel(max_retries=0)

    llm_classify(
        dataframe=dataframe,
        template=RAG_RELEVANCY_PROMPT_TEMPLATE,
        model=model,
        rails=["relevant", "irrelevant"],
        verbose=True,
        use_function_calling_if_available=False,
    )

    out, _ = capfd.readouterr()
    assert "Snapped 'relevant' to rail: relevant" in out, "Snapping events should be printed"
    assert "Snapped 'irrelevant' to rail: irrelevant" in out, "Snapping events should be printed"
    assert "Snapped '\\nrelevant ' to rail: relevant" in out, "Snapping events should be printed"
    assert "Cannot snap 'unparsable' to rails" in out, "Snapping events should be printed"
    assert "OpenAI invocation parameters" in out, "Model-specific information should be printed"
    assert "'model': 'gpt-4', 'temperature': 0.0" in out, "Model information should be printed"
    assert "sk-0123456789" not in out, "Credentials should not be printed out in cleartext"


def test_llm_classify_shows_retry_info(openai_api_key: str, capfd: pytest.CaptureFixture[str]):
    dataframe = pd.DataFrame(
        [
            {
                "input": "What is Python?",
                "reference": "Python is a programming language.",
            },
        ]
    )

    with ExitStack() as stack:
        waiting_fn = "phoenix.experimental.evals.models.base.wait_random_exponential"
        stack.enter_context(patch(waiting_fn, return_value=False))
        model = OpenAIModel(max_retries=4)

        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        openai_retry_errors = [
            model._openai.APITimeoutError("test timeout"),
            model._openai.APIError(
                message="test api error",
                request=httpx.request,
                body={},
            ),
            model._openai.APIConnectionError(message="test api connection error", request=request),
            model._openai.InternalServerError(
                "test internal server error",
                response=httpx.Response(status_code=500, request=request),
                body={},
            ),
        ]
        mock_openai = MagicMock()
        mock_openai.side_effect = openai_retry_errors
        stack.enter_context(
            patch.object(model._async_client.chat.completions, "create", mock_openai)
        )
        llm_classify(
            dataframe=dataframe,
            template=RAG_RELEVANCY_PROMPT_TEMPLATE,
            model=model,
            rails=["relevant", "irrelevant"],
        )

    out, _ = capfd.readouterr()
    assert "Failed attempt 1" in out, "Retry information should be printed"
    assert "Failed attempt 2" in out, "Retry information should be printed"
    assert "Failed attempt 3" in out, "Retry information should be printed"
    assert "Failed attempt 4" not in out, "Maximum retries should not be exceeded"


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_run_relevance_eval_standard_dataframe(
    openai_api_key: str,
    respx_mock: respx.mock,
):
    dataframe = pd.DataFrame(
        [
            {
                "input": "What is Python?",
                "reference": [
                    "Python is a programming language.",
                    "Ruby is a programming language.",
                ],
            },
            {
                "input": "Can you explain Python to me?",
                "reference": np.array(
                    [
                        "Python is a programming language.",
                        "Ruby is a programming language.",
                    ]
                ),
            },
            {
                "input": "What is Ruby?",
                "reference": [
                    "Ruby is a programming language.",
                ],
            },
            {
                "input": "What is C++?",
                "reference": [
                    "Ruby is a programming language.",
                    "C++ is a programming language.",
                ],
            },
            {
                "input": "What is C#?",
                "reference": [],
            },
            {
                "input": "What is Golang?",
                "reference": None,
            },
            {
                "input": None,
                "reference": [
                    "Python is a programming language.",
                    "Ruby is a programming language.",
                ],
            },
            {
                "input": None,
                "reference": None,
            },
        ]
    )

    queries = list(dataframe["input"])
    references = list(dataframe["reference"])
    keys = []
    for query, refs in zip(queries, references):
        refs = refs if refs is None else list(refs)
        if query and refs:
            keys.extend(product([query], refs))

    responses = [
        "relevant",
        "irrelevant",
        "relevant",
        "irrelevant",
        "\nrelevant ",
        "unparsable",
        "relevant",
    ]

    response_mapping = {key: response for key, response in zip(keys, responses)}
    for (query, reference), response in response_mapping.items():
        matcher = M(content__contains=query) & M(content__contains=reference)
        payload = {
            "choices": [
                {
                    "message": {
                        "content": response,
                    },
                }
            ],
            "usage": {
                "total_tokens": 1,
            },
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    with patch.object(OpenAIModel, "_init_tiktoken", return_value=None):
        model = OpenAIModel()

    relevance_classifications = run_relevance_eval(dataframe, model=model)
    assert relevance_classifications == [
        ["relevant", "irrelevant"],
        ["relevant", "irrelevant"],
        ["relevant"],
        [NOT_PARSABLE, "relevant"],
        [],
        [],
        [],
        [],
    ]


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions", assert_all_called=False)
def test_classify_tolerance_to_exceptions(
    openai_api_key: str,
    classification_dataframe: pd.DataFrame,
    classification_responses: List[str],
    classification_template: str,
    respx_mock: respx.mock,
    capfd,
):
    with patch.object(OpenAIModel, "_init_tiktoken", return_value=None):
        model = OpenAIModel(max_retries=0)
    queries = classification_dataframe["input"].tolist()
    for query, response in zip(queries, classification_responses):
        matcher = M(content__contains=query)
        # Simulate an error on the second query
        if query == "What is C++?":
            response = httpx.Response(500, json={"error": "Internal Server Error"})
        else:
            response = httpx.Response(200, json={"choices": [{"message": {"content": response}}]})
        respx_mock.route(matcher).mock(return_value=response)

    classification_df = llm_classify(
        dataframe=classification_dataframe,
        template=classification_template,
        model=model,
        rails=["relevant", "irrelevant"],
    )

    assert classification_df is not None
    # Make sure there is a logger.error output
    captured = capfd.readouterr()
    assert "Exception in worker" in captured.out


def test_run_relevance_eval_openinference_dataframe(
    openai_api_key: str,
    respx_mock: respx.mock,
):
    dataframe = pd.DataFrame(
        [
            {
                "attributes.input.value": "What is Python?",
                "attributes.retrieval.documents": [
                    {"document.content": "Python is a programming language."},
                    {"document.content": "Ruby is a programming language."},
                ],
            },
            {
                "attributes.input.value": "Can you explain Python to me?",
                "attributes.retrieval.documents": np.array(
                    [
                        {"document.content": "Python is a programming language."},
                        {"document.content": "Ruby is a programming language."},
                    ]
                ),
            },
            {
                "attributes.input.value": "What is Ruby?",
                "attributes.retrieval.documents": [
                    {"document.content": "Ruby is a programming language."},
                ],
            },
            {
                "attributes.input.value": "What is C++?",
                "attributes.retrieval.documents": [
                    {"document.content": "Ruby is a programming language."},
                    {"document.content": "C++ is a programming language."},
                ],
            },
            {
                "attributes.input.value": "What is C#?",
                "attributes.retrieval.documents": [],
            },
            {
                "attributes.input.value": "What is Golang?",
                "attributes.retrieval.documents": None,
            },
            {
                "attributes.input.value": None,
                "attributes.retrieval.documents": [
                    {"document.content": "Python is a programming language."},
                    {"document.content": "Ruby is a programming language."},
                ],
            },
            {
                "attributes.input.value": None,
                "attributes.retrieval.documents": None,
            },
        ]
    )

    queries = list(dataframe["attributes.input.value"])
    references = list(dataframe["attributes.retrieval.documents"])
    keys = []
    for query, refs in zip(queries, references):
        refs = refs if refs is None else list(refs)
        if query and refs:
            keys.extend(product([query], refs))
    keys = [(query, ref["document.content"]) for query, ref in keys]

    responses = [
        "relevant",
        "irrelevant",
        "relevant",
        "irrelevant",
        "\nrelevant ",
        "unparsable",
        "relevant",
    ]

    response_mapping = {key: response for key, response in zip(keys, responses)}
    for (query, reference), response in response_mapping.items():
        matcher = M(content__contains=query) & M(content__contains=reference)
        payload = {
            "choices": [
                {
                    "message": {
                        "content": response,
                    },
                }
            ],
            "usage": {
                "total_tokens": 1,
            },
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    with patch.object(OpenAIModel, "_init_tiktoken", return_value=None):
        model = OpenAIModel()

    relevance_classifications = run_relevance_eval(dataframe, model=model)
    assert relevance_classifications == [
        ["relevant", "irrelevant"],
        ["relevant", "irrelevant"],
        ["relevant"],
        [NOT_PARSABLE, "relevant"],
        [],
        [],
        [],
        [],
    ]


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_run_evals_outputs_dataframes_with_labels_and_explanations_when_invoked_with_function_calls(
    running_event_loop_mock: bool,
    respx_mock: respx.mock,
    toxicity_evaluator: LLMEvaluator,
    relevance_evaluator: LLMEvaluator,
) -> None:
    for matcher, label, explanation in [
        (
            M(content__contains="Paris is the capital of France.")
            & M(content__contains="relevant"),
            "relevant",
            "relevant-explanation",
        ),
        (
            M(content__contains="Munich is the capital of Germany.")
            & M(content__contains="relevant"),
            "irrelevant",
            "irrelevant-explanation",
        ),
        (
            M(content__contains="What is the capital of France?") & M(content__contains="toxic"),
            "non-toxic",
            "non-toxic-explanation",
        ),
    ]:
        payload = {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "function_call": {
                            "name": _FUNCTION_NAME,
                            "arguments": json.dumps({_RESPONSE: label, _EXPLANATION: explanation}),
                        },
                    },
                    "finish_reason": "function_call",
                }
            ],
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    df = pd.DataFrame(
        [
            {
                "input": "What is the capital of France?",
                "reference": "Paris is the capital of France.",
            },
            {
                "input": "What is the capital of France?",
                "reference": "Munich is the capital of Germany.",
            },
        ],
        index=["a", "b"],
    )
    eval_dfs = run_evals(
        dataframe=df,
        evaluators=[relevance_evaluator, toxicity_evaluator],
        provide_explanation=True,
        use_function_calling_if_available=True,
    )
    assert len(eval_dfs) == 2
    assert_frame_equal(
        eval_dfs[0],
        pd.DataFrame(
            {
                "label": ["relevant", "irrelevant"],
                "explanation": [
                    "relevant-explanation",
                    "irrelevant-explanation",
                ],
            },
            index=["a", "b"],
        ),
    )
    assert_frame_equal(
        eval_dfs[1],
        pd.DataFrame(
            {
                "label": ["non-toxic", "non-toxic"],
                "explanation": [
                    "non-toxic-explanation",
                    "non-toxic-explanation",
                ],
            },
            index=["a", "b"],
        ),
    )


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_run_evals_outputs_dataframes_with_labels_and_explanations(
    running_event_loop_mock: bool,
    respx_mock: respx.mock,
    toxicity_evaluator: LLMEvaluator,
    relevance_evaluator: LLMEvaluator,
) -> None:
    for matcher, response in [
        (
            M(content__contains="Paris is the capital of France.")
            & M(content__contains="relevant"),
            "relevant-explanation\nLABEL: relevant",
        ),
        (
            M(content__contains="Munich is the capital of Germany.")
            & M(content__contains="relevant"),
            "irrelevant-explanation\nLABEL: irrelevant",
        ),
        (
            M(content__contains="What is the capital of France?") & M(content__contains="toxic"),
            "non-toxic-explanation\nLABEL: non-toxic",
        ),
    ]:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": response,
                    },
                }
            ],
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    df = pd.DataFrame(
        [
            {
                "input": "What is the capital of France?",
                "reference": "Paris is the capital of France.",
            },
            {
                "input": "What is the capital of France?",
                "reference": "Munich is the capital of Germany.",
            },
        ],
        index=["a", "b"],
    )
    eval_dfs = run_evals(
        dataframe=df,
        evaluators=[relevance_evaluator, toxicity_evaluator],
        provide_explanation=True,
        use_function_calling_if_available=False,
    )
    assert len(eval_dfs) == 2
    assert_frame_equal(
        eval_dfs[0],
        pd.DataFrame(
            {
                "label": ["relevant", "irrelevant"],
                "explanation": [
                    "relevant-explanation\nLABEL: relevant",
                    "irrelevant-explanation\nLABEL: irrelevant",
                ],
            },
            index=["a", "b"],
        ),
    )
    assert_frame_equal(
        eval_dfs[1],
        pd.DataFrame(
            {
                "label": ["non-toxic", "non-toxic"],
                "explanation": [
                    "non-toxic-explanation\nLABEL: non-toxic",
                    "non-toxic-explanation\nLABEL: non-toxic",
                ],
            },
            index=["a", "b"],
        ),
    )


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_run_evals_outputs_dataframes_with_just_labels_when_invoked_with_function_calls(
    running_event_loop_mock: bool,
    respx_mock: respx.mock,
    toxicity_evaluator: LLMEvaluator,
    relevance_evaluator: LLMEvaluator,
) -> None:
    for matcher, response in [
        (
            M(content__contains="Paris is the capital of France.")
            & M(content__contains="relevant"),
            "relevant",
        ),
        (
            M(content__contains="Munich is the capital of Germany.")
            & M(content__contains="relevant"),
            "irrelevant",
        ),
        (
            M(content__contains="What is the capital of France?") & M(content__contains="toxic"),
            "non-toxic",
        ),
    ]:
        payload = {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "function_call": {
                            "name": _FUNCTION_NAME,
                            "arguments": json.dumps(
                                {
                                    _RESPONSE: response,
                                }
                            ),
                        },
                    },
                    "finish_reason": "function_call",
                }
            ],
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    df = pd.DataFrame(
        [
            {
                "input": "What is the capital of France?",
                "reference": "Paris is the capital of France.",
            },
            {
                "input": "What is the capital of France?",
                "reference": "Munich is the capital of Germany.",
            },
        ],
        index=["a", "b"],
    )
    eval_dfs = run_evals(
        dataframe=df,
        evaluators=[relevance_evaluator, toxicity_evaluator],
        provide_explanation=False,
        use_function_calling_if_available=True,
    )
    assert len(eval_dfs) == 2
    assert_frame_equal(
        eval_dfs[0],
        pd.DataFrame(
            {"label": ["relevant", "irrelevant"]},
            index=["a", "b"],
        ),
    )
    assert_frame_equal(
        eval_dfs[1],
        pd.DataFrame(
            {"label": ["non-toxic", "non-toxic"]},
            index=["a", "b"],
        ),
    )


@pytest.mark.respx(base_url="https://api.openai.com/v1/chat/completions")
def test_run_evals_outputs_dataframes_with_just_labels(
    running_event_loop_mock: bool,
    respx_mock: respx.mock,
    toxicity_evaluator: LLMEvaluator,
    relevance_evaluator: LLMEvaluator,
) -> None:
    for matcher, response in [
        (
            M(content__contains="Paris is the capital of France.")
            & M(content__contains="relevant"),
            "relevant",
        ),
        (
            M(content__contains="Munich is the capital of Germany.")
            & M(content__contains="relevant"),
            "irrelevant",
        ),
        (
            M(content__contains="What is the capital of France?") & M(content__contains="toxic"),
            "non-toxic",
        ),
    ]:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": response,
                    },
                }
            ],
        }
        respx_mock.route(matcher).mock(return_value=httpx.Response(200, json=payload))

    df = pd.DataFrame(
        [
            {
                "input": "What is the capital of France?",
                "reference": "Paris is the capital of France.",
            },
            {
                "input": "What is the capital of France?",
                "reference": "Munich is the capital of Germany.",
            },
        ],
        index=["a", "b"],
    )
    eval_dfs = run_evals(
        dataframe=df,
        evaluators=[relevance_evaluator, toxicity_evaluator],
        provide_explanation=False,
        use_function_calling_if_available=False,
    )
    assert len(eval_dfs) == 2
    assert_frame_equal(
        eval_dfs[0],
        pd.DataFrame(
            {"label": ["relevant", "irrelevant"]},
            index=["a", "b"],
        ),
    )
    assert_frame_equal(
        eval_dfs[1],
        pd.DataFrame(
            {"label": ["non-toxic", "non-toxic"]},
            index=["a", "b"],
        ),
    )


def test_run_evals_with_empty_evaluators_returns_empty_list() -> None:
    eval_dfs = run_evals(
        dataframe=pd.DataFrame(),
        evaluators=[],
    )
    assert eval_dfs == []
