import configs.iris as cfg
from utils.utils import *
from utils.data_loading import load_processed_dataset
import os
from CSDGAN.classes.tabular.TabularCGAN import TabularCGAN
from CSDGAN.classes.tabular.TabularDataset import TabularDataset
from torch.utils import data
import pickle as pkl
import random

# Set random seem for reproducibility
print("Random Seed: ", cfg.MANUAL_SEED)
random.seed(cfg.MANUAL_SEED)
torch.manual_seed(cfg.MANUAL_SEED)

# Ensure directory exists for outputs
exp_path = os.path.join("experiments", cfg.EXPERIMENT_NAME)

# Import data
iris = load_processed_dataset('iris')

# Automatically determine these parameters and complete preprocessing
device = torch.device("cuda:0" if (torch.cuda.is_available()) else "cpu")
out_dim = iris.shape[1]
labels_list = list(iris[cfg.DEP_VAR].unique())

# Instantiate data set and generator
dataset = TabularDataset(df=iris,
                         dep_var=cfg.DEP_VAR,
                         cont_inputs=cfg.CONT_INPUTS,
                         int_inputs=cfg.INT_INPUTS,
                         test_size=cfg.TEST_SIZE,
                         seed=cfg.MANUAL_SEED)
dataset.to_dev(device)
data_gen = data.DataLoader(dataset, **cfg.TRAINING_PARAMS)
eval_stratify = list(dataset.y_train.mean(0).detach().cpu().numpy())

# Define GAN
CGAN = TabularCGAN(data_gen=data_gen,
                   device=device,
                   path=exp_path,
                   seed=cfg.MANUAL_SEED,
                   eval_param_grid=cfg.EVAL_PARAM_GRID,
                   eval_folds=cfg.EVAL_FOLDS,
                   test_ranges=cfg.TEST_RANGES,
                   eval_stratify=eval_stratify,
                   **cfg.CGAN_INIT_PARAMS)

# Eval on real data
score_real = train_test_logistic_reg(x_train=CGAN.data_gen.dataset.x_train.cpu().detach().numpy(),
                                     y_train=CGAN.data_gen.dataset.y_train.cpu().detach().numpy(),
                                     x_test=CGAN.data_gen.dataset.x_test.cpu().detach().numpy(),
                                     y_test=CGAN.data_gen.dataset.y_test.cpu().detach().numpy(),
                                     param_grid=cfg.EVAL_PARAM_GRID,
                                     cv=cfg.EVAL_FOLDS,
                                     random_state=cfg.MANUAL_SEED,
                                     labels_list=labels_list,
                                     verbose=True)

# Train GAN
CGAN.train_gan(num_epochs=cfg.NUM_EPOCHS, cadence=cfg.CADENCE, print_freq=cfg.PRINT_FREQ, eval_freq=cfg.EVAL_FREQ)

# Load best-performing GAN
CGAN.load_netG(best=True)

# Fit another model to double-check results
CGAN.test_model(stratify=CGAN.eval_stratify)

# Save GAN
with open(os.path.join(exp_path, "CGAN.pkl"), 'wb') as f:
    pkl.dump(CGAN, f)

# Visualizations
CGAN.plot_progress(benchmark_acc=score_real, show=True, save=exp_path)
CGAN.plot_training_plots(show=True, save=exp_path)
CGAN.netG.plot_layer_scatters(show=True, save=exp_path)
CGAN.netD.plot_layer_scatters(show=True, save=exp_path)
CGAN.netG.plot_layer_hists(show=True, save=exp_path)
CGAN.netD.plot_layer_hists(show=True, save=exp_path)

genned_df = CGAN.gen_data(size=cfg.TEST_RANGES[3], stratify=eval_stratify)
plot_scatter_matrix(df=genned_df, cont_inputs=cfg.CONT_INPUTS, title="Fake Data", scaler=None, show=True, save=exp_path)
plot_scatter_matrix(df=iris, cont_inputs=cfg.CONT_INPUTS, title="Real Data", scaler=None, show=True, save=exp_path)

class_dict = {1: ('Iris-setosa', 'r'),
              2: ('Iris-versicolor', 'b'),
              3: ('Iris-virginica', 'g')}

plot_conditional_scatter(col1='sepal_len',
                         col2='sepal_wid',
                         real_df=iris,
                         fake_df=genned_df,
                         dep_var=cfg.DEP_VAR,
                         cont_inputs=cfg.CONT_INPUTS,
                         labels_list=labels_list,
                         scaler=None,
                         alpha=0.25,
                         show=True,
                         save=exp_path)

plot_conditional_density(col='petal_len',
                         real_df=iris,
                         fake_df=genned_df,
                         dep_var=cfg.DEP_VAR,
                         cont_inputs=cfg.CONT_INPUTS,
                         labels_list=labels_list,
                         scaler=None,
                         show=True,
                         save=exp_path)
