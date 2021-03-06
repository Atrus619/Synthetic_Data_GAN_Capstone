from utils.data_loading import load_raw_dataset
from classes.wine.CGAN_wine import CGAN_Generator, CGAN_Discriminator
from utils.utils import *
import random

# Set random seem for reproducibility
manualSeed = 999
print("Random Seed: ", manualSeed)
random.seed(manualSeed)
torch.manual_seed(manualSeed)

# Import data
wine = load_raw_dataset('wine')
wine.head()

# Split 50-50 so we can demonstrate the effectiveness of additional data
x_train, x_test, y_train, y_test = train_test_split(wine.drop(columns='class'), wine['class'], test_size=88, stratify=wine['class'], random_state=manualSeed)

# Parameters
nz = 64  # Size of generator noise input
H = 32  # Size of hidden network layer
out_dim = x_train.shape[1]  # Size of output
bs = x_train.shape[0]  # Full data set
nc = 3  # 3 different types of label in this problem
num_batches = 1
num_epochs = 10000
print_interval = 1000
exp_name = 'experiments/wine_1x32_wd_0'
safe_mkdir(exp_name)

# Adam optimizer hyperparameters
lr = 2e-4
beta1 = 0.5
beta2 = 0.999

# Set the device
# device = torch.device("cuda:0" if (torch.cuda.is_available()) else "cpu")
device = 'cpu'

# Scale inputs
scaler = StandardScaler()
x_train = scaler.fit_transform(x_train)
x_train_tensor = torch.tensor(x_train, dtype=torch.float)
y_train_dummies = pd.get_dummies(y_train)
y_train_dummies_tensor = torch.tensor(y_train_dummies.values, dtype=torch.float)

# Instantiate nets
netG = CGAN_Generator(nz=nz, H=H, out_dim=out_dim, nc=nc, bs=bs, device=device, wd=0).to(device)
netD = CGAN_Discriminator(H=H, out_dim=out_dim, nc=nc, device=device, wd=0).to(device)

# Print classes
print(netG)
print(netD)

# Define labels
real_label = 1
fake_label = 0

# Train on real data
y_test_dummies = pd.get_dummies(y_test)
print("Dummy columns match?", all(y_train_dummies.columns == y_test_dummies.columns))
x_test = scaler.transform(x_test)
labels_list = [x for x in y_train_dummies.columns]
param_grid = {'tol': [1e-9],
              'C': [0.5],
              'l1_ratio': [0]}
model_real, score_real = train_test_logistic_reg(x_train, y_train, x_test, y_test, param_grid=param_grid, cv=5, random_state=manualSeed, labels=labels_list)

# For diagnostics
test_range = [90, 180, 360, 720, 1440]
stored_models = []
stored_scores = []
best_score = 0

# Train GAN
print("Starting Training Loop...")
for epoch in range(num_epochs):
    for i in range(num_batches):  # Only one batch per epoch since our data is horrifically small
        # Update Discriminator
        # All real batch first
        real_data = x_train_tensor.to(device)  # Format batch (entire data set in this case)
        real_classes = y_train_dummies_tensor.to(device)
        label = torch.full((bs,), real_label, device=device)  # All real labels

        output = netD(real_data, real_classes).view(-1)  # Forward pass with real data through Discriminator
        netD.train_one_step_real(output, label)

        # All fake batch next
        noise = torch.randn(bs, nz, device=device)  # Generate batch of latent vectors
        fake = netG(noise, real_classes)  # Fake image batch with netG
        label.fill_(fake_label)
        output = netD(fake.detach(), real_classes).view(-1)
        netD.train_one_step_fake(output, label)
        netD.combine_and_update_opt()
        netD.update_history()

        # Update Generator
        label.fill_(real_label)  # Reverse labels, fakes are real for generator cost
        output = netD(fake, real_classes).view(-1)  # Since D has been updated, perform another forward pass of all-fakes through D
        netG.train_one_step(output, label)
        netG.update_history()

    # Output training stats
    if epoch % print_interval == 0 or (epoch == num_epochs-1):
        print('[%d/%d]\tLoss_D: %.4f\tLoss_G: %.4f\tD(x): %.4f\tD(G(z)): %.4f / %.4f'
                % (epoch+1, num_epochs, netD.loss.item(), netG.loss.item(), netD.D_x, netD.D_G_z1, netG.D_G_z2))
        with torch.no_grad():
            # Generate various levels of amounts of fake data and test how training compares
            tmp_models, tmp_scores = evaluate_training_progress(test_range=test_range, fake_bs=bs, nz=nz, nc=nc, out_dim=out_dim, netG=netG,
                                                                x_test=x_test, y_test=y_test, manualSeed=manualSeed, labels_list=labels_list,
                                                                param_grid=param_grid, device=device)
        if max(tmp_scores) > best_score:
            best_score = max(tmp_scores)
            torch.save(netG.state_dict(), exp_name + "/best_netG.pt")
        stored_models += tmp_models
        stored_scores += tmp_scores

# Load best model
best_netG = CGAN_Generator(nz=nz, H=H, out_dim=out_dim, nc=nc, bs=bs, device=device, wd=0).to(device)
best_netG.load_state_dict(torch.load(exp_name + "/best_netG.pt"))

# Plot evaluation over time
plot_training_progress(stored_scores=stored_scores, test_range=test_range, num_saves=len(stored_scores) // len(test_range), save=exp_name)

# Example parsing a model for stats
parse_models(stored_models=stored_models, epoch=9000, print_interval=print_interval, test_range=test_range,
             ind=3, x_test=x_test, y_test=y_test, labels=labels_list)

# Output plots
training_plots(netD=netD, netG=netG, num_epochs=num_epochs, save=exp_name)
plot_layer_scatters(netG, title="Generator", save=exp_name)
plot_layer_scatters(netD, title="Discriminator", save=exp_name)

# Generate one last set of fake data for diagnostics
genned_data, genned_labels = gen_fake_data(netG=best_netG, bs=360, nz=nz, nc=nc, labels_list=labels_list, device=device)
model_fake, score_fake = train_test_logistic_reg(genned_data, genned_labels, x_test, y_test, param_grid=param_grid, cv=5, random_state=manualSeed, labels=labels_list)

# Visualize distributions
plot_scatter_matrix(genned_data, "Fake Data", wine.drop(columns='class'), scaler=scaler, save=exp_name)
plot_scatter_matrix(wine.drop(columns='class'), "Real Data", wine.drop(columns='class'), scaler=None, save=exp_name)

# Conditional scatters
# Class dict
class_dict = {1: ('Class 1', 'r'),
              2: ('Class 2', 'b'),
              3: ('Class 3', 'g')}
plot_conditional_scatter(x_real=np.concatenate((x_train, x_test), axis=0),
                         y_real=np.concatenate((y_train, y_test), axis=0),
                         x_fake=genned_data,
                         y_fake=genned_labels,
                         col1=11,
                         col2=12,
                         class_dict=class_dict,
                         og_df=wine.drop(columns='class'),
                         scaler=scaler,
                         alpha=0.25,
                         save=exp_name)

# Conditional densities
plot_conditional_density(x_real=np.concatenate((x_train, x_test), axis=0),
                         y_real=np.concatenate((y_train, y_test), axis=0),
                         x_fake=genned_data,
                         y_fake=genned_labels,
                         col=10,
                         class_dict=class_dict,
                         og_df=wine.drop(columns='class'),
                         scaler=scaler,
                         save=exp_name)


