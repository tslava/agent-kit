import boto3
from aws_cdk import App, Duration, Environment, Stack
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_lambda as lambda_
from constructs import Construct


class InventoryApiStack(Stack):
    def __init__(self, scope: Construct, id: str, env: Environment) -> None:
        super().__init__(scope, id, env=env)
        ssm = boto3.client("ssm", region_name=env.region)
        dsn = ssm.get_parameter(Name="/dev/inventory/db/dsn", WithDecryption=True)["Parameter"]["Value"]

        fn = lambda_.Function(
            self, "InventoryApiLambda",
            runtime=lambda_.Runtime.PYTHON_3_14,
            handler="app.app",
            code=lambda_.Code.from_asset("out/deployment.zip"),
            timeout=Duration.seconds(25),
            environment={"DATABASE_DSN": dsn},
        )
        apigateway.LambdaRestApi(self, "InventoryApi", handler=fn)


app = App()
InventoryApiStack(app, "InventoryApi", env=Environment(region="us-east-1"))
app.synth()
