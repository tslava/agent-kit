import boto3
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_lambda as lambda_
from aws_cdk import core
from aws_cdk.core import Duration, Environment


class InventoryApiStack(core.Stack):
    def __init__(self, app: core.App, id: str, env: Environment) -> None:
        super().__init__(app, id, env=env)
        ssm = boto3.client("ssm", region_name=env.region)
        dsn = ssm.get_parameter(Name="/dev/inventory/db/dsn", WithDecryption=True)["Parameter"]["Value"]

        fn = lambda_.Function(
            self, "InventoryApiLambda",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="app.app",
            code=lambda_.Code.asset("out/deployment.zip"),
            timeout=Duration.seconds(25),
            environment={"DATABASE_DSN": dsn},
        )
        apigateway.LambdaRestApi(self, "InventoryApi", handler=fn)


app = core.App()
InventoryApiStack(app, "InventoryApi", env=Environment(region="us-east-1"))
app.synth()
