from airflow.models import DAG, Variable
from operators.papermill_minio import PapermillMinioOperator
from airflow.operators.bash import BashOperator
from datetime import timedelta, datetime
from airflow.utils.dates import days_ago


AIRFLOW_DAG_HOME='/opt/airflow/dags/'
TMP_FOLDER='/tmp/'
DAG_FOLDER = 'dag_schema_data_gouv_fr/'
DAG_NAME = 'schemas_backend'

MINIO_URL = Variable.get("minio_url")
MINIO_BUCKET = Variable.get("minio_bucket_opendata")
MINIO_USER = Variable.get("secret_minio_user_opendata")
MINIO_PASSWORD = Variable.get("secret_minio_password_opendata")

GIT_REPO = 'git@github.com:etalab/schema.data.gouv.fr.git'

default_args = {
   'email': ['geoffrey.aldebert@data.gouv.fr'],
   'email_on_failure': True
}

with DAG(
    dag_id=DAG_NAME,
    schedule_interval='0 2 * * *',
    start_date=days_ago(1),
    dagrun_timeout=timedelta(minutes=60),
    tags=['schemas','backend','datagouv','schema.data.gouv.fr'],
    default_args=default_args,
) as dag:
    
    clean_previous_outputs = BashOperator(
        task_id='clean_previous_outputs',
        bash_command='rm -rf ' + TMP_FOLDER + DAG_FOLDER+'{{ ds }}' + "/" + \
            ' && mkdir -p ' + TMP_FOLDER + DAG_FOLDER + '{{ ds }}' + "/",
    )

    clone_schema_repo = BashOperator(
        task_id='clone_schema_repo',
        bash_command='cd ' + TMP_FOLDER + DAG_FOLDER + '{{ ds }}' + "/ " + \
            '&& git clone ' + GIT_REPO ,
    )
    
    run_nb = PapermillMinioOperator(
        task_id="run_notebook_schemas_backend",
        input_nb=AIRFLOW_DAG_HOME + DAG_FOLDER + "notebooks/schemas_backend.ipynb",
        output_nb='{{ ds }}' + ".ipynb",
        tmp_path=TMP_FOLDER + DAG_FOLDER+'{{ ds }}' + "/",
        minio_url=MINIO_URL,
        minio_bucket=MINIO_BUCKET,
        minio_user=MINIO_USER,
        minio_password=MINIO_PASSWORD,
        minio_output_filepath='datagouv/schemas_backend/' + '{{ ds }}' + "/",
        parameters={
            "msgs": "Ran from Airflow " + '{{ ds }}' + "!",
            "WORKING_DIR": AIRFLOW_DAG_HOME + DAG_FOLDER,
            "TMP_FOLDER": TMP_FOLDER + DAG_FOLDER + '{{ ds }}' + "/",
            "OUTPUT_DATA_FOLDER": TMP_FOLDER + DAG_FOLDER + '{{ ds }}' + "/output/",
            "DATE_AIRFLOW": '{{ ds }}',
            "LIST_SCHEMAS_YAML": 'https://raw.githubusercontent.com/etalab/schema.data.gouv.fr/master/repertoires.yml'
        }
    )

    copy_files = BashOperator(
        task_id='copy_files',
        bash_command='cd ' + TMP_FOLDER + DAG_FOLDER + '{{ ds }}' + "/" + \
            ' && mkdir site' + \
            ' && cp -r schema.data.gouv.fr/site/site/*.md ./site/' + \
            ' && cp -r schema.data.gouv.fr/site/site/.vuepress/ ./site/' + \
            ' && rm -rf ./site/.vuepress/public/schemas' + \
            ' && mkdir ./site/.vuepress/public/schemas' + \
            ' && cp -r data/* ./site/ ' + \
            ' && cp -r data2/* ./site/.vuepress/public/schemas' + \
            ' && cp ./site/.vuepress/public/schemas/*.json ./site/.vuepress/public/' + \
            ' && rm -rf ./schema.data.gouv.fr/site/site' + \
            ' && mv ./site ./schema.data.gouv.fr/site/'
    )

    commit_changes = BashOperator(
        task_id='commit_changes',
        bash_command='cd ' + TMP_FOLDER + DAG_FOLDER + '{{ ds }}' + "/schema.data.gouv.fr" + \
            ' && git add site/site/'+ \
            ' && git commit -m "Update Website ' + datetime.today().strftime('%Y-%m-%d') + '" || echo "No changes to commit"' \
            ' && git push origin master'
    )

    clean_previous_outputs >> clone_schema_repo >> run_nb >> copy_files >> commit_changes
