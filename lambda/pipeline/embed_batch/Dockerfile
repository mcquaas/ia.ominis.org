# Lambda container image for embed_batch (sentence-transformers). Build and push to ECR, then create Lambda from image.
FROM public.ecr.aws/lambda/python:3.12

RUN pip install --no-cache-dir sentence-transformers boto3

COPY embed_batch/handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
