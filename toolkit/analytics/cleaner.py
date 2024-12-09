import copy
import pandas as pd
from pathlib import Path
from datetime import datetime

from toolkit.system.storage.data_io_tools import load_pickle, save_pickle
from toolkit.system.logging_tools import Logger

logger = Logger(name="cleaner").get_logger()

pd.set_option("future.no_silent_downcasting", True)


def remove_invalid_characters_from_sheet_name(sheet_name):
    invalid_chars = [":", "/", "\\", "?", "*", "[", "]"]
    for char in invalid_chars:
        sheet_name = sheet_name.replace(char, "_")
    return sheet_name


def get_datetime_run_id():
    current_datetime = datetime.now().strftime("%Y%m%d%H%M%S")
    return current_datetime


class Cleaner:
    def __init__(self):

        self._paths = {}
        self._dirs = {}

        self.identifiers = []  # For containing identifiers

    def configure_run(self, input_df, run_id=None, df_name=None):

        self.input_df = copy.deepcopy(input_df)

        if run_id is None:
            self.run_id = get_datetime_run_id()
        else:
            self.run_id = run_id

        self.df_name = df_name

    def create_column_report(self):
        self._initialize_paths()
        self._set_df()

        self._sort_columns()
        overview_sheet = self._get_overview_sheet()
        num_sheet, num_edit_sheet = self._get_num_sheet()
        cat_sheet, cat_edit_sheet = self._get_cat_sheet()

        with pd.ExcelWriter(self._paths["col_report"]) as writer:
            overview_sheet.to_excel(writer, sheet_name="overview", index=False)
            num_sheet.to_excel(writer, sheet_name="num_stats", index=False)
            num_edit_sheet.to_excel(writer, sheet_name="num_todo", index=False)
            cat_sheet.to_excel(writer, sheet_name="cat_stats", index=False)
            cat_edit_sheet.to_excel(writer, sheet_name="cat_todo", index=False)

    def _initialize_paths(self):

        self._dirs["results"] = Path(f"analytics/{self.run_id}/cleaner")
        self._dirs["results"].mkdir(exist_ok=True, parents=True)

        if self.df_name is not None:
            self._dirs["df"] = self._dirs["results"] / self.df_name
            self._dirs["df"].mkdir(exist_ok=True, parents=True)
        else:
            self._dirs["df"] = self.results_dir

        self._paths["df"] = Path(f"{self._dirs['df']}/df.csv")
        self._paths["clean_df"] = self._dirs["df"] / "df_clean.csv"
        # self._paths["metadata"] = self._dirs["df"] / "metadata.pkl"

        self._paths["col_report"] = self._dirs["df"] / "column_report.xlsx"
        self._paths["col_report_for_changes"] = (
            self._dirs["df"] / "column_report_for_changes.xlsx"
        )
        self._paths["col_report_cleaned"] = self._dirs["df"] / "col_report_cleaned.xlsx"

        # self._dirs["col_reports"] = self._dirs["df"] / "col_reports"
        # self._dirs["col_reports"].mkdir(exist_ok=True, parents=True)

        # self._dirs["clean_col_reports"] = self._dirs["df"] / "col_reports_clean"
        # self._dirs["clean_col_reports"].mkdir(exist_ok=True, parents=True)

        # self._paths["num_col_names"] = (self._dirs["col_reports"] / "col_names_num.pkl")
        # self._paths["cat_col_names"] = (self._dirs["col_reports"] / "col_names_cat.pkl")
        # self._paths["clean_cat_cols_report"] = (self._dirs["clean_col_reports"] / "col_report_cat.xlsx")
        # self._paths["clean_num_cols_report"] = (self._dirs["clean_col_reports"] / "col_report_num.csv")
        # self._paths["clean_num_col_names"] = (self._dirs["clean_col_reports"] / "col_names_num.pkl")
        # self._paths["clean_cat_col_names"] = (self._dirs["clean_col_reports"] / "col_names_cat.pkl")
        # self._paths["identifiers"] = (self._dirs["clean_col_reports"] / "identifiers.pkl")

    def _set_df(self):

        if self._paths["clean_df"].exists():
            self.df = pd.read_csv(self._paths["clean_df"])
            logger.info(
                f"clean DataFrame Exists at {self._paths['clean_df']}, No Need for processing."
            )

        elif self._paths["df"].exists():
            self.df = pd.read_csv(self._paths["df"])
            logger.info(
                f"DataFrame saved before with identical configuration at {self._dirs['df']}."
            )

        else:
            self.df = self.input_df
            self.df.to_csv(self._paths["df"], index=False)

    # def _load_metadata(self):
    #     if self._paths["metadata"].exists():
    #         logger.info("Metadata exists")
    #         self._metadata = load_pickle(self._metadata_path)
    #     else:
    #         self._metadata = {}

    def _sort_columns(self):
        self._all_col_names = self.df.columns.tolist()
        self.sorted_col_names = {}
        self.sorted_col_names["num"] = self.df.select_dtypes(
            include=["number"]
        ).columns.tolist()
        self.sorted_col_names["cat"] = self.df.select_dtypes(
            include=["object", "category"]
        ).columns.tolist()
        self.sorted_col_names["datetime"] = self.df.select_dtypes(
            include=["datetime"]
        ).columns.tolist()
        self.sorted_col_names["other"] = self.df.select_dtypes(
            exclude=["number", "object", "category", "datetime"]
        ).columns.tolist()

    def _get_overview_sheet(self):
        overview_sheet = []
        for key, value in self.sorted_col_names.items():
            temp_dict = {}
            temp_dict["col_type"] = key
            temp_dict["n_col_names"] = len(value)
            overview_sheet.append(temp_dict)

        temp_dict = {}
        temp_dict["col_type"] = "identifiers"
        temp_dict["n_col_names"] = 0
        overview_sheet.append(temp_dict)

        temp_dict = {}
        temp_dict["col_type"] = "Total"
        temp_dict["n_col_names"] = len(self._all_col_names)
        overview_sheet.append(temp_dict)

        overview_sheet = pd.DataFrame(overview_sheet)

        for col_type, col_names in self.sorted_col_names.items():
            overview_sheet, col_names = self._insert_column_in_df(
                overview_sheet, col_names
            )
            overview_sheet[f"{col_type}_col_names"] = col_names

        identifier_cols = []
        overview_sheet, identifier_cols = self._insert_column_in_df(
            overview_sheet, identifier_cols
        )
        overview_sheet["identifier_columns"] = identifier_cols

        overview_sheet, all_columns = self._insert_column_in_df(
            overview_sheet, self._all_col_names
        )
        overview_sheet["all_columns"] = all_columns

        return overview_sheet

    def _get_num_sheet(self):
        num_col_names = self.sorted_col_names["num"]

        num_sheet = []
        for num_col_name in num_col_names:
            col = self.df[num_col_name]
            temp_dict = {}
            temp_dict["col_name"] = num_col_name
            temp_dict["n_observations"] = len(col)
            temp_dict["min"] = col.min()
            temp_dict["max"] = col.max()
            temp_dict["median"] = col.median()
            temp_dict["q1"] = col.quantile(0.25)
            temp_dict["q3"] = col.quantile(0.75)
            temp_dict["mean"] = col.mean()
            temp_dict["std"] = col.std()
            num_sheet.append(temp_dict)
        num_sheet = pd.DataFrame(num_sheet)

        num_edit_sheet = []
        for num_col_name in num_col_names:
            temp_dict = {}
            temp_dict["col_name"] = num_col_name
            temp_dict["numerical"] = True
            temp_dict["add_to_identifiers"] = pd.NA
            temp_dict["add_to_categorical"] = pd.NA
            temp_dict["remove_from_analysis"] = pd.NA
            temp_dict["rename_to"] = pd.NA
            num_edit_sheet.append(temp_dict)
        num_edit_sheet = pd.DataFrame(num_edit_sheet)

        return num_sheet, num_edit_sheet

    def _get_cat_sheet(self):
        cat_sheet = pd.DataFrame()
        cat_col_names = self.sorted_col_names["cat"]

        for cat_col_name in cat_col_names:
            col = self.df[cat_col_name]
            value_counts = col.value_counts()

            categories = value_counts.keys().to_list()
            counts = value_counts.values.tolist()

            cat_sheet, categories = self._insert_column_in_df(cat_sheet, categories)
            cat_sheet[cat_col_name] = categories

            if len(categories) == len(counts):
                cat_sheet[f"(Counts) {cat_col_name}"] = counts
            else:
                cat_sheet, counts = self._insert_column_in_df(cat_sheet, counts)
                cat_sheet[f"(Counts) {cat_col_name}"] = counts

            cat_sheet, empty_column = self._insert_column_in_df(cat_sheet, [pd.NA])
            cat_sheet[f"(RenameDict) {cat_col_name}"] = empty_column

        cat_edit_sheet = []
        for num_col_name in cat_col_names:
            temp_dict = {}
            temp_dict["col_name"] = num_col_name
            temp_dict["categorical"] = True
            temp_dict["add_to_identifiers"] = pd.NA
            temp_dict["add_to_numerical"] = pd.NA
            temp_dict["remove_from_analysis"] = pd.NA
            temp_dict["rename_to"] = pd.NA
            cat_edit_sheet.append(temp_dict)
        cat_edit_sheet = pd.DataFrame(cat_edit_sheet)

        return cat_sheet, cat_edit_sheet

    def _prepare_for_changes(self):
        self.df = pd.read_csv(self._paths["df"])

        if self._paths["col_report_for_changes"].exists():
            self._col_report_for_changes = pd.ExcelFile(
                self._paths["col_report_for_changes"]
            )
        else:
            raise ValueError(
                f"No col_report_for_changes found at path {col_report_for_changes}"
            )

        self._overview = self._col_report_for_changes.parse("overview", index_col=None)

        self.cat_col_names = self._overview["cat_col_names"].dropna().to_list()
        self.num_col_names = self._overview["num_col_names"].dropna().to_list()

        self._num_todo = self._col_report_for_changes.parse(
            "num_todo", index_col=None
        ).fillna(False)
        self._cat_todo = self._col_report_for_changes.parse(
            "cat_todo", index_col=None
        ).fillna(False)

        self._cat_stats = self._col_report_for_changes.parse(
            "cat_stats", index_col=None
        )

        self._remove_cols = []  # At the dataframe level
        self._rename_cols = {}  # At the dataframe level
        self._rename_labels = {}

    def _clean_categorical_cols(self):
        for row in self._cat_todo.itertuples(index=False):
            col_name = row.col_name
            remove_from_analysis = row.remove_from_analysis
            rename_to = row.rename_to
            add_to_identifiers = row.add_to_identifiers
            add_to_numerical = row.add_to_numerical

            if remove_from_analysis:
                self._remove_cols.append(col_name)
                logger.info(
                    f"{col_name} will be completely removed from further analysis."
                )
                self.cat_col_names.remove(col_name)
                # self.df = self.df.drop(columns=[col_name])
                continue

            if rename_to:
                self._rename_cols[col_name] = rename_to
                logger.info(f"{col_name}  renamed to {rename_to}.")
                col_name = rename_to

                # self.df = self.df.rename(columns={col_name: rename_to})

            if add_to_identifiers:
                self.identifiers.append(col_name)
                self.num_col_names.remove(col_name)
                logger.info(f"{col_name}  added to identifiers.")
            elif add_to_numerical:
                self.num_col_names.append(col_name)
                self.cat_col_names.remove(col_name)
                logger.info(
                    f"Category changed from categorical to numerical for {col_name}"
                )

    def _clean_numerical_cols(self):
        for row in self._num_todo.itertuples(index=False):
            col_name = row.col_name
            remove_from_analysis = row.remove_from_analysis
            rename_to = row.rename_to
            add_to_identifiers = row.add_to_identifiers
            add_to_categorical = row.add_to_categorical

            if remove_from_analysis:
                self._remove_cols.append(col_name)
                logger.info(
                    f"{col_name} will be completely removed from further analysis."
                )
                self.num_col_names.remove(col_name)
                continue

            if rename_to:
                self._rename_cols[col_name] = rename_to
                logger.info(f"{col_name}  renamed to {rename_to}.")
                col_name = rename_to

            if add_to_identifiers:
                self.identifiers.append(col_name)
                self.num_col_names.remove(col_name)
                logger.info(f"{col_name}  added to identifiers.")
            elif add_to_categorical:
                self.cat_col_names.append(col_name)
                self.num_col_names.remove(col_name)
                logger.info(
                    f"Category changed from numerical to categorical for {col_name}"
                )

    def _prepare_label_rename_dicts(self):
        for cat_col_name in self.cat_col_names:
            cat_col_stats = self._cat_stats[
                [
                    cat_col_name,
                    f"(Counts) {cat_col_name}",
                    f"(RenameDict) {cat_col_name}",
                ]
            ]
            rename_df = cat_col_stats[
                [cat_col_name, f"(RenameDict) {cat_col_name}"]
            ].dropna()
            if rename_df.shape[0] != 0:
                rename_dict = dict(
                    zip(
                        rename_df[cat_col_name],
                        rename_df[f"(RenameDict) {cat_col_name}"],
                    )
                )
                self._rename_labels[cat_col_name] = rename_dict

    def _commit_changes(self):
        if not self.identifiers:
            logger.warning(f"No identifiers suggested, please check.")

        if self._rename_labels:
            for cat_col_name, rename_dict in self._rename_labels.items():
                self.df[cat_col_name] = self.df[cat_col_name].replace(rename_dict)

        if self._remove_cols:
            self.df = self.df.drop(columns=self._remove_cols)

        if self._rename_cols:
            self.df = self.df.rename(columns=self._rename_cols)

    def clean(self):

        self._prepare_for_changes()
        self._clean_categorical_cols()
        self._clean_numerical_cols()
        self._prepare_label_rename_dicts()
        self._commit_changes()

        columns_accounted_for = (
            len(self.cat_col_names) + len(self.num_col_names) + len(self.identifiers)
        )
        total_columns = self.df.shape[1]
        assert (
            columns_accounted_for == total_columns
        ), f"{total_columns-columns_accounted_for}  unaccounted columns exists in df."

        self._create_clean_df()
        self._create_clean_col_report()

    def _create_clean_col_report(self):
        cleaned_overview_sheet = self._get_cleaned_overview_sheet()

        with pd.ExcelWriter(self._paths["col_report_cleaned"]) as writer:
            cleaned_overview_sheet.to_excel(writer, sheet_name="overview", index=False)

    def _create_clean_df(self):
        self.df.to_csv(self._paths["clean_df"], index=False)

    def _get_cleaned_overview_sheet(self):

        cleaned_overview_sheet = pd.DataFrame()
        cleaned_overview_sheet["identifiers"] = self.identifiers
        cleaned_overview_sheet, self.cat_col_names = self._insert_column_in_df(
            cleaned_overview_sheet, self.cat_col_names
        )
        cleaned_overview_sheet["cat_col_names"] = self.cat_col_names
        cleaned_overview_sheet, self.num_col_names = self._insert_column_in_df(
            cleaned_overview_sheet, self.num_col_names
        )
        cleaned_overview_sheet["num_col_names"] = self.num_col_names

        return cleaned_overview_sheet

    @staticmethod
    def _insert_column_in_df(df, column):
        if len(column) > len(df):
            df = df.reindex(range(len(column)))
            return df, column
        else:
            padded_data = column + [pd.NA] * (len(df) - len(column))
            return df, padded_data
