import os
import time
import pytest
from unittest.mock import patch

import pandas as pd

from mindsdb_sql import parse_sql

from tests.unit.executor_test_base import BaseExecutorTest


OPEN_AI_API_KEY = os.environ.get("OPEN_AI_API_KEY")
os.environ["OPENAI_API_KEY"] = OPEN_AI_API_KEY


class TestOpenAI(BaseExecutorTest):
    def wait_predictor(self, project, name):
        # wait
        done = False
        for attempt in range(200):
            ret = self.run_sql(f"select * from {project}.models where name='{name}'")
            if not ret.empty:
                if ret["STATUS"][0] == "complete":
                    done = True
                    break
                elif ret["STATUS"][0] == "error":
                    break
            time.sleep(0.5)
        if not done:
            raise RuntimeError("predictor wasn't created")

    def run_sql(self, sql):
        ret = self.command_executor.execute_command(parse_sql(sql, dialect="mindsdb"))
        assert ret.error_code is None
        if ret.data is not None:
            columns = [col.alias if col.alias is not None else col.name for col in ret.columns]
            return pd.DataFrame(ret.data, columns=columns)

    def test_missing_required_keys(self):
        # create project
        self.run_sql("create database proj")
        with pytest.raises(Exception):
            self.run_sql(
                f"""
                  create model proj.test_openai_missing_required_keys
                  predict answer
                  using
                    engine='openai',
                    openai_api_key='{OPEN_AI_API_KEY}';
               """
            )

    def test_invalid_openai_name_parameter(self):
        # create project
        self.run_sql("create database proj")
        self.run_sql(
            f"""
              create model proj.test_openai_nonexistant_model
              predict answer
              using
                engine='openai',
                question_column='question',
                model_name='this-gpt-does-not-exist',
                openai_api_key='{OPEN_AI_API_KEY}';
           """
        )
        with pytest.raises(Exception):
            self.wait_predictor("proj", "test_openai_nonexistant_model")

    @patch("mindsdb.integrations.handlers.postgres_handler.Handler")
    def test_qa_no_context(self, mock_handler):
        # create project
        self.run_sql("create database proj")
        df = pd.DataFrame.from_dict({"question": [
            "What is the capital of Sweden?",
            "What is the second planet of the solar system?"
        ]})
        self.set_handler(mock_handler, name="pg", tables={"df": df})

        self.run_sql(
            f"""
           create model proj.test_openai_qa_no_context
           predict answer
           using
             engine='openai',
             question_column='question',
             openai_api_key='{OPEN_AI_API_KEY}';
        """
        )
        self.wait_predictor("proj", "test_openai_qa_no_context")

        result_df = self.run_sql(
            """
            SELECT p.answer
            FROM proj.test_openai_qa_no_context as p
            WHERE question='What is the capital of Sweden?'
        """
        )
        assert "stockholm" in result_df["answer"].iloc[0].lower()

        result_df = self.run_sql(
            """
            SELECT p.answer
            FROM pg.df as t
            JOIN proj.test_openai_qa_no_context as p;
        """
        )
        assert "stockholm" in result_df["answer"].iloc[0].lower()
        assert "venus" in result_df["answer"].iloc[1].lower()

    @patch("mindsdb.integrations.handlers.postgres_handler.Handler")
    def test_qa_context(self, mock_handler):
        # create project
        self.run_sql("create database proj")
        df = pd.DataFrame.from_dict({"question": [
            "What is the capital of Sweden?",
            "What is the second planet of the solar system?"
        ], "context": ['Add "Boom!" to the end of the answer.', 'Add "Boom!" to the end of the answer.']})
        self.set_handler(mock_handler, name="pg", tables={"df": df})

        self.run_sql(
            f"""
           create model proj.test_openai_qa_context
           predict answer
           using
             engine='openai',
             question_column='question',
             context_column='context',
             openai_api_key='{OPEN_AI_API_KEY}';
        """
        )
        self.wait_predictor("proj", "test_openai_qa_context")

        result_df = self.run_sql(
            """
            SELECT p.answer
            FROM proj.test_openai_qa_context as p
            WHERE
            question='What is the capital of Sweden?' AND
            context='Add "Boom!" to the end of the answer.'
        """
        )
        assert "stockholm" in result_df["answer"].iloc[0].lower()
        assert "boom!" in result_df["answer"].iloc[0].lower()

        result_df = self.run_sql(
            """
            SELECT p.answer
            FROM pg.df as t
            JOIN proj.test_openai_qa_context as p;
        """
        )
        assert "stockholm" in result_df["answer"].iloc[0].lower()
        assert "venus" in result_df["answer"].iloc[1].lower()

        for i in range(2):
            assert "boom!" in result_df["answer"].iloc[i].lower()

    @patch("mindsdb.integrations.handlers.postgres_handler.Handler")
    def test_prompt_template(self, mock_handler):
        # create project
        self.run_sql("create database proj")
        df = pd.DataFrame.from_dict({"question": [
            "What is the capital of Sweden?",
            "What is the second planet of the solar system?"
        ]})
        self.set_handler(mock_handler, name="pg", tables={"df": df})
        self.run_sql(
            f"""
           create model proj.test_openai_prompt_template
           predict completion
           using
             engine='openai',
             prompt_template='Answer this question and add "Boom!" to the end of the answer: {{{{question}}}}',
             openai_api_key='{OPEN_AI_API_KEY}';
        """
        )
        self.wait_predictor("proj", "test_openai_prompt_template")

        result_df = self.run_sql(
            """
            SELECT p.completion
            FROM proj.test_openai_prompt_template as p
            WHERE
            question='What is the capital of Sweden?';
        """
        )
        assert "stockholm" in result_df["completion"].iloc[0].lower()
        assert "boom!" in result_df["completion"].iloc[0].lower()

        result_df = self.run_sql(
            """
            SELECT p.completion
            FROM pg.df as t
            JOIN proj.test_openai_prompt_template as p;
        """
        )
        assert "stockholm" in result_df["completion"].iloc[0].lower()
        assert "venus" in result_df["completion"].iloc[1].lower()

        for i in range(2):
            assert "boom!" in result_df["completion"].iloc[i].lower()
