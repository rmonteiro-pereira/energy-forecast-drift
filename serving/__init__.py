"""FastAPI serving for the registry champion (M5).

`serving.app` exposes `/forecast`, which loads
`models:/energy-demand-forecaster@champion` from the MLflow registry — an
alias, never a path — so promoting a model is a registry operation and not a
deploy.

Nothing is re-exported here on purpose: binding the name `app` in this package
would shadow the `serving.app` **module**, and `import serving.app` would then
hand you a `FastAPI` instance instead. Import from the module directly:

    from serving.app import create_app
    uvicorn serving.app:app
"""
