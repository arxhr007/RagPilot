from __future__ import annotations

from app.analysis.analyzer import analyze_dataset, build_architecture
from app.orchestration.router import answer_question
from app.store import Dataset


def run_dataset_graph(dataset: Dataset) -> Dataset:
    try:
        from langgraph.graph import END, StateGraph
        from typing_extensions import TypedDict

        class State(TypedDict):
            dataset: Dataset

        def analyze(state: State) -> State:
            state["dataset"].analysis = analyze_dataset(state["dataset"])
            return state

        def architecture(state: State) -> State:
            state["dataset"].architecture = build_architecture(state["dataset"])
            return state

        graph = StateGraph(State)
        graph.add_node("analyze_dataset", analyze)
        graph.add_node("build_pipeline", architecture)
        graph.set_entry_point("analyze_dataset")
        graph.add_edge("analyze_dataset", "build_pipeline")
        graph.add_edge("build_pipeline", END)
        return graph.compile().invoke({"dataset": dataset})["dataset"]
    except Exception:
        dataset.analysis = analyze_dataset(dataset)
        dataset.architecture = build_architecture(dataset)
        return dataset


def run_query_graph(dataset: Dataset, question: str, route_override: str = "auto"):
    try:
        from langgraph.graph import END, StateGraph
        from typing_extensions import TypedDict

        class State(TypedDict):
            dataset: Dataset
            question: str
            route_override: str
            response: object

        def classify_and_route(state: State) -> State:
            state["response"] = answer_question(state["dataset"], state["question"], state["route_override"])
            return state

        graph = StateGraph(State)
        graph.add_node("classify_query", classify_and_route)
        graph.set_entry_point("classify_query")
        graph.add_edge("classify_query", END)
        return graph.compile().invoke({"dataset": dataset, "question": question, "route_override": route_override, "response": None})["response"]
    except Exception:
        return answer_question(dataset, question, route_override)
